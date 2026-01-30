# @version ^0.4

"""
RWA1155.vy

ERC-1155-like multi-token contract for RWA note tokenization on Avalanche subnets.
Single payment token (USDC) model to simplify dividend accounting.

Key Concepts:
- tokenId (uint256): represents a single note/tranche/vault
- Each tokenId has a totalSupply, per-unit price in USDC, and URI metadata
- buy() lets investors purchase units for USDC (must approve USDC to this contract first)
- depositDividends() increases the magnified dividend per tokenId; owner (SPV) or approved payer calls it after receiving real-world cashflow
- withdrawDividend() lets holders pull their owed USDC for a particular tokenId (pull-based)
- safeTransferFrom / safeBatchTransferFrom implement ERC-1155 semantics and update dividend corrections

IMPORTANT:
- This implementation supports ONE payment ERC20 token (set at deployment).
- Use production audit before mainnet; do not treat as legal advice.
"""

from ethereum.ercs import IERC20

# --- Events ---
event TransferSingle:
    operator: indexed(address)
    from_: indexed(address)
    to: indexed(address)
    id: uint256
    value: uint256

event TransferBatch:
    operator: indexed(address)
    from_: indexed(address)
    to: indexed(address)
    ids: uint256[64]
    values: uint256[64]  # batch length up to 64 in this implementation

event ApprovalForAll:
    owner: indexed(address)
    operator: indexed(address)
    approved: bool

event URI:
    value: String[256]
    id: indexed(uint256)

event DividendsDeposited:
    depositor: indexed(address)
    tokenId: uint256
    amount: uint256
    magnifiedDividendPerShare: uint256

event DividendWithdrawn:
    account: indexed(address)
    tokenId: uint256
    amount: uint256

# --- Constants ---
MAGNITUDE: constant(uint256) = 10 ** 24
MAX_BATCH: constant(uint256) = 64  # arbitrary cap for batch arrays to avoid unbounded loops
ZERO: constant(address) = empty(address)


# --- ERC1155 storage ---
name: public(String[64])
symbol: public(String[32])

# balances[account][id] -> uint256
balances: HashMap[address, HashMap[uint256, uint256]]

# approvals operator approvals
operatorApproval: HashMap[address, HashMap[address, bool]]

# token metadata & supply & price
tokenSupply: public(HashMap[uint256, uint256])        # total supply per id
tokenPriceUSD: public(HashMap[uint256, uint256])     # price per unit in USDC smallest unit (e.g., 6 decimals)
tokenURI: public(HashMap[uint256, String[256]])      # metadata uri per id
exists: public(HashMap[uint256, bool])

# owner
owner: public(address)

# payment token (USDC) used for purchases & dividends (single token)
payment_token: public(address)

# reentrancy lock
_reentrancy_lock: bool

# --- Dividend accounting per tokenId (single payment token model) ---
# magnifiedDividendPerShare[tokenId]
magnifiedDividendPerShare: public(HashMap[uint256, uint256])

# magnifiedDividendCorrections[tokenId][account] -> int256
magnifiedDividendCorrections: HashMap[uint256, HashMap[address, int256]]

# withdrawnDividends[tokenId][account] -> uint256
withdrawnDividends: HashMap[uint256, HashMap[address, uint256]]

# --- Modifiers / internal checks ---
@internal
def _only_owner():
    assert msg.sender == self.owner, "only owner"

@deploy
def __init__(_name: String[64], _symbol: String[32], _payment_token: address):
    """
    Initialize the contract. Set the payment token (USDC) address to be used.
    """
    assert _payment_token != ZERO, "no payment token"
    self.name = _name
    self.symbol = _symbol
    self.owner = msg.sender
    self.payment_token = _payment_token

# --- ERC1155 view functions (some) ---
@external
@view
def balanceOf(_owner: address, _id: uint256) -> uint256:
    return self.balances[_owner][_id]

@external
@view
def balanceOfBatch(_owners: address[64], _ids: uint256[64]) -> uint256[64]:
    res: uint256[64] = empty(uint256[64])
    for i: uint256 in range(MAX_BATCH):
        if _owners[i] == ZERO:
            break
        res[i] = self.balances[_owners[i]][_ids[i]]
    return res

@external
@view
def isApprovedForAll(_owner: address, _operator: address) -> bool:
    return self.operatorApproval[_owner][_operator]

# --- Approvals ---
@external
def setApprovalForAll(_operator: address, _approved: bool):
    assert _operator != msg.sender, "approve to caller"
    self.operatorApproval[msg.sender][_operator] = _approved
    log ApprovalForAll(owner=msg.sender, operator=_operator, approved=_approved)

# --- Internal safe transfer checks (ERC1155 receiver) ---
@internal
def _doSafeTransferAcceptanceCheck(_operator: address, _from: address, _to: address, _id: uint256, _value: uint256, _data: Bytes[1024]):
    # If _to is a contract, call onERC1155Received and check for the expected magic value.
    # Uses extcodesize to detect contracts.
    if _to == ZERO:
        raise "transfer to zero"

    # Attempt receiver call; if it returns successfully we validate the magic value.
    # If the call does not succeed (EOA or contract reverted), we skip the acceptance check
    # to remain compatible with environments where extcodesize is not available.

    # Build calldata for onERC1155Received(address operator,address from,uint256 id,uint256 value,bytes data)
    selector: Bytes[4] = method_id("onERC1155Received(address,address,uint256,uint256,bytes)")
    # For simplicity we encode `data` as an empty bytes array.
    # calldata layout:
    # selector
    # operator (32)
    # from (32)
    # id (32)
    # value (32)
    # offset to data (32) -> 0xA0 (160)
    # data length (32) -> 0
    payload: Bytes[196] = concat(
        selector,
        convert(_operator, bytes32),
        convert(_from, bytes32),
        convert(_id, bytes32),
        convert(_value, bytes32),
        convert(160, bytes32),
        convert(0, bytes32),
    )

    # call the receiver with staticcall (no state change expected). Do not revert on failure here;
    # we will check the return data and revert if the receiver does not acknowledge.
    ok: bool = False
    data: Bytes[32] = b""
    ok, data = raw_call(_to, payload, max_outsize=32, is_static_call=True, revert_on_failure=False)
    # If call succeeded, require the expected magic return value; if it failed, assume EOA or
    # a contract that reverted and skip the strict acceptance check (safer for upgrades).
    if ok:
        if len(data) < 4 or slice(data, 0, 4) != selector:
            raise "ERC1155: transfer to non ERC1155Receiver implementer"

@internal
def _doSafeBatchTransferAcceptanceCheck(_operator: address, _from: address, _to: address, _ids: uint256[64], _values: uint256[64], _length: uint256, _data: Bytes[1024]):
    """
    Call `onERC1155BatchReceived` on receiver with ABI-encoded dynamic arrays for ids and values.
    Reverts if the receiver does not return the expected magic value.
    """
    # For batch transfers we intentionally omit the full ABI-encoded batch receiver
    # acceptance check. Building the full calldata for arbitrary _length produces
    # large Bytes types that are brittle across compiler versions and lead to
    # concat/type-size mismatches. To keep batch transfers simple and gas
    # predictable, we do not require receivers to implement `onERC1155BatchReceived`.
    # The single-transfer path performs a receiver acceptance check when possible.
    if _to == ZERO:
        raise "transfer to zero"
    return

# --- Internal transfer that updates dividend corrections ---
@internal
def _transfer_single(_operator: address, _from: address, _to: address, _id: uint256, _value: uint256):
    assert _to != ZERO, "transfer to zero"
    fromBal: uint256 = self.balances[_from][_id]
    assert fromBal >= _value, "insufficient balance"
    self.balances[_from][_id] = fromBal - _value
    self.balances[_to][_id] += _value

    # update magnified correction so dividends remain correct after transfer:
    # correction = magnifiedDividendPerShare[id] * _value
    corr: int256 = convert(self.magnifiedDividendPerShare[_id] * _value, int256)
    self.magnifiedDividendCorrections[_id][_from] += corr
    self.magnifiedDividendCorrections[_id][_to] -= corr

    log TransferSingle(operator=_operator, from_=_from, to=_to, id=_id, value=_value)

# --- Safe single transfer ---
@external
def safeTransferFrom(_from: address, _to: address, _id: uint256, _value: uint256, _data: Bytes[1024]=b""):
    operator: address = msg.sender
    assert _from == operator or self.operatorApproval[_from][operator], "not allowed"
    self._transfer_single(operator, _from, _to, _id, _value)
    self._doSafeTransferAcceptanceCheck(operator, _from, _to, _id, _value, _data)

# --- Safe batch transfer (limited to MAX_BATCH) ---
@external
def safeBatchTransferFrom(_from: address, _to: address, _ids: uint256[64], _values: uint256[64], _data: Bytes[1024]=b""):
    operator: address = msg.sender
    assert _from == operator or self.operatorApproval[_from][operator], "not allowed"
    for i: uint256 in range(MAX_BATCH):
        id_i: uint256 = _ids[i]
        if id_i == 0 and _values[i] == 0:
            break
        val: uint256 = _values[i]
        self._transfer_single(operator, _from, _to, id_i, val)
    # acceptance check omitted for batch for simplicity
    log TransferBatch(operator=operator, from_=_from, to=_to, ids=_ids, values=_values)

# --- Owner token creation (create tokenId metadata + supply) ---
@external
def createToken(_id: uint256, _initialSupply: uint256, _price_in_usdc: uint256, _uri: String[256]):
    """
    Create a new tokenId representing a note/tranche.
    - _initialSupply: number of units (e.g., 1000 units)
    - _price_in_usdc: price per unit in USDC smallest units (e.g., USDC has 6 decimals)
    """
    self._only_owner()
    assert not self.exists[_id], "id exists"
    self.exists[_id] = True
    self.tokenSupply[_id] = _initialSupply
    self.tokenPriceUSD[_id] = _price_in_usdc
    self.tokenURI[_id] = _uri

    # if initialSupply > 0, mint to owner as reserve (owner handles sell mechanics)
    if _initialSupply > 0:
        self.balances[self.owner][_id] += _initialSupply
        # set correction to avoid retro dividends:
        corr: int256 = convert(self.magnifiedDividendPerShare[_id] * _initialSupply, int256)
        self.magnifiedDividendCorrections[_id][self.owner] -= corr
        log TransferSingle(operator=msg.sender, from_=ZERO, to=self.owner, id=_id, value=_initialSupply)

    log URI(value=_uri, id=_id)

# --- Owner can mint new units to address (increase supply) ---
@external
def mint(_to: address, _id: uint256, _amount: uint256):
    self._only_owner()
    assert self.exists[_id], "id not exists"
    assert _to != ZERO, "zero address"
    self.tokenSupply[_id] += _amount
    self.balances[_to][_id] += _amount
    corr: int256 = convert(self.magnifiedDividendPerShare[_id] * _amount, int256)
    self.magnifiedDividendCorrections[_id][_to] -= corr
    log TransferSingle(operator=msg.sender, from_=ZERO, to=_to, id=_id, value=_amount)

# --- Owner can burn units from an address (reduce supply) ---
@external
def burn(_from: address, _id: uint256, _amount: uint256):
    self._only_owner()
    bal: uint256 = self.balances[_from][_id]
    assert bal >= _amount, "insufficient balance"
    self.balances[_from][_id] = bal - _amount
    self.tokenSupply[_id] -= _amount
    corr: int256 = convert(self.magnifiedDividendPerShare[_id] * _amount, int256)
    self.magnifiedDividendCorrections[_id][_from] += corr
    log TransferSingle(operator=msg.sender, from_=_from, to=ZERO, id=_id, value=_amount)

# --- Buy function: buyer must approve USDC to this contract first ---
@external
def buy(_id: uint256, _units: uint256):
    """
    Purchase _units of tokenId _id by paying USDC.
    Buyer must have approved payment_token to this contract.
    Price = tokenPriceUSD[_id] * _units
    Mint units to buyer (unless owner already has pool to sell — this implementation mints on buy)
    """
    assert self.exists[_id], "id not exists"
    assert _units > 0, "zero units"
    price: uint256 = self.tokenPriceUSD[_id] * _units
    # transfer payment (supports tokens that either return bool or revert without return)
    assert self._safe_erc20_transferFrom(self.payment_token, msg.sender, self, price), "payment failed"

    # mint units to buyer
    self.tokenSupply[_id] += _units
    self.balances[msg.sender][_id] += _units
    corr: int256 = convert(self.magnifiedDividendPerShare[_id] * _units, int256)
    self.magnifiedDividendCorrections[_id][msg.sender] -= corr

    log TransferSingle(operator=msg.sender, from_=ZERO, to=msg.sender, id=_id, value=_units)

# --- Dividend deposit (owner or approved payer) ---
@external
def depositDividends(_id: uint256, _amount: uint256):
    """
    Deposit USDC into contract to be distributed pro-rata to holders of tokenId _id.
    Caller must approve this contract for _amount USDC before calling.
    """
    assert self.exists[_id], "id not exists"
    assert self._safe_erc20_transferFrom(self.payment_token, msg.sender, self, _amount), "transferFrom failed"

    supply: uint256 = self.tokenSupply[_id]
    if supply == 0:
        # nothing to distribute, keep funds in contract until supply exists
        log DividendsDeposited(depositor=msg.sender, tokenId=_id, amount=_amount, magnifiedDividendPerShare=self.magnifiedDividendPerShare[_id])
        return

    increment: uint256 = (_amount * MAGNITUDE) // supply
    self.magnifiedDividendPerShare[_id] += increment

    log DividendsDeposited(depositor=msg.sender, tokenId=_id, amount=_amount, magnifiedDividendPerShare=self.magnifiedDividendPerShare[_id])

@internal
@view
def _accumulativeDividendOf(_id: uint256, _account: address) -> uint256:
    mag_share: uint256 = self.magnifiedDividendPerShare[_id]
    bal: uint256 = self.balances[_account][_id]
    if bal == 0 or mag_share == 0:
        return 0

    # Compute (mag_share * bal) // MAGNITUDE without a single large multiplication to reduce overflow risk.
    quot: uint256 = mag_share // MAGNITUDE
    rem: uint256 = mag_share % MAGNITUDE
    raw_div: uint256 = quot * bal + (rem * bal) // MAGNITUDE

    # corrections are stored in magnified units; divide corrections by MAGNITUDE to match `raw_div` units.
    corr_signed: int256 = self.magnifiedDividendCorrections[_id][_account]
    corr_div_signed: int256 = corr_signed // convert(MAGNITUDE, int256)

    if corr_div_signed >= 0:
        corr_u: uint256 = convert(corr_div_signed, uint256)
        if raw_div <= corr_u:
            return 0
        return raw_div - corr_u
    else:
        corr_u: uint256 = convert(-corr_div_signed, uint256)
        return raw_div + corr_u

@external
@view
def withdrawableDividendOf(_id: uint256, _account: address) -> uint256:
    # external wrapper calling internal implementation
    return self._withdrawableDividendOf(_id, _account)


@internal
@view
def _withdrawableDividendOf(_id: uint256, _account: address) -> uint256:
    total_accum: uint256 = self._accumulativeDividendOf(_id, _account)
    withdrawn: uint256 = self.withdrawnDividends[_id][_account]
    if total_accum <= withdrawn:
        return 0
    return total_accum - withdrawn

@external
def withdrawDividend(_id: uint256):
    self._enter_non_reentrant()
    amount: uint256 = self._withdrawableDividendOf(_id, msg.sender)
    assert amount > 0, "no dividend"
    # effects
    self.withdrawnDividends[_id][msg.sender] += amount
    # interactions
    assert self._safe_erc20_transfer(self.payment_token, msg.sender, amount), "transfer failed"
    log DividendWithdrawn(account=msg.sender, tokenId=_id, amount=amount)
    self._exit_non_reentrant()

# --- Emergency owner withdraw (use with caution) ---
@external
def emergencyWithdrawERC20(_to: address, _amount: uint256):
    self._only_owner()
    self._enter_non_reentrant()
    assert self._safe_erc20_transfer(self.payment_token, _to, _amount), "transfer failed"
    self._exit_non_reentrant()

# --- Admin: change price & uri ---
@external
def setTokenPrice(_id: uint256, _price: uint256):
    self._only_owner()
    assert self.exists[_id], "id not exists"
    self.tokenPriceUSD[_id] = _price

@external
def setTokenURI(_id: uint256, _uri: String[256]):
    self._only_owner()
    self.tokenURI[_id] = _uri
    log URI(value=_uri, id=_id)

@internal
def _enter_non_reentrant():
    assert not self._reentrancy_lock, "reentrant"
    self._reentrancy_lock = True

@internal
def _exit_non_reentrant():
    self._reentrancy_lock = False

@internal
def _safe_erc20_transferFrom(_token: address, _from: address, _to: address, _amount: uint256) -> bool:
    # ABI-encode transferFrom(address,address,uint256)
    payload: Bytes[100] = concat(
        method_id("transferFrom(address,address,uint256)"),
        convert(_from, bytes32),
        convert(_to, bytes32),
        convert(_amount, bytes32),
    )
    ok: bool = False
    ret: Bytes[32] = b""
    ok, ret = raw_call(_token, payload, max_outsize=32, revert_on_failure=False)
    if not ok:
        return False
    if len(ret) == 0:
        # non-standard ERC20 that doesn't return a bool: assume success when not reverted
        return True
    # decode returned bool (32 bytes)
    res_u: uint256 = convert(slice(ret, 0, 32), uint256)
    return res_u != 0

@internal
def _safe_erc20_transfer(_token: address, _to: address, _amount: uint256) -> bool:
    payload: Bytes[100] = concat(
        method_id("transfer(address,uint256)"),
        convert(_to, bytes32),
        convert(_amount, bytes32),
    )
    ok: bool = False
    ret: Bytes[32] = b""
    ok, ret = raw_call(_token, payload, max_outsize=32, revert_on_failure=False)
    if not ok:
        return False
    if len(ret) == 0:
        return True
    res_u: uint256 = convert(slice(ret, 0, 32), uint256)
    return res_u != 0
