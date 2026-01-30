# @version ^0.4

"""
RWALite.vy

ERC-1155-like multi-token contract for RWA note tokenization on Avalanche subnets.
A lite version of the original RWA1155.vy focusing on core functionality and single person functions.
Single payment token (USDC) model to simplify dividend accounting.

Key Concepts:
- tokenId (uint256): represents a single note/tranche/vault
- Each tokenId has a totalSupply, per-unit price in USDC, and URI metadata
- buy() lets investors purchase units for USDC (must approve USDC to this contract first)
- depositDividends() increases the magnified dividend per tokenId; owner (SPV) or approved payer calls it after receiving real-world cashflow
- withdrawableDividendOf() lets holders check their withdrawable USDC dividends per tokenId
- safeTransferFrom implements ERC-1155 semantics and update dividend corrections
- Owner can mint/burn tokens to manage supply

IMPORTANT:
- This implementation supports ONE payment ERC20 token (set at deployment).
- Use production audit before mainnet; do not treat as legal advice.
"""

from ethereum.ercs import IERC20

# --- Events ---
event TokenCreated:
    id:            indexed(uint256)
    initialSupply: uint256
    priceUSDC:     uint256
    uri:           String[256]
    fingerprint:   bytes32

event TransferSingle:
    operator: indexed(address)
    from_: indexed(address)
    to: indexed(address)
    id: uint256
    value: uint256

event Paused:
    account: indexed(address)

event Unpaused:
    account: indexed(address)

event MaturitySet:
    tokenId: indexed(uint256)
    maturityTime: uint64
    
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

event OwnershipTransferred:
    previousOwner: indexed(address)
    newOwner:      indexed(address)

# Standard ERC-1155 Interface IDs
# 0xd9b67a26 = ERC1155
# 0x01ffc9a7 = ERC165
SUPPORTED_INTERFACES: constant(bytes32[2]) = [
    0x01ffc9a700000000000000000000000000000000000000000000000000000000,
    0xd9b67a2600000000000000000000000000000000000000000000000000000000
]

# --- Constants ---
MAGNITUDE: constant(uint256) = 10 ** 24
MAX_BATCH: constant(uint256) = 64  # arbitrary cap for batch arrays to avoid unbounded loops
ZERO: constant(address) = empty(address)


# --- ERC1155 storage ---
name: public(String[64])                # Name of contract
symbol: public(String[32])               # SYmbol of contract

# payment token (USDC) used for purchases & dividends (single token)
payment_token: public(address)

# balances[account][id] -> uint256
balances: HashMap[address, HashMap[uint256, uint256]]

# approvals operator approvals
operatorApproval: HashMap[address, HashMap[address, bool]]

# token metadata & supply & price
tokenSupply: public(HashMap[uint256, uint256])        # total supply per id
tokenPriceUSD: public(HashMap[uint256, uint256])     # price per unit in USDC smallest unit (e.g., 6 decimals)
tokenURI: public(HashMap[uint256, String[256]])      # metadata uri per id
exists: public(HashMap[uint256, bool])              # Duplication prevention of loan ids

# owner
owner: public(address)

# ---- Pause Contract ----
paused: public(bool)


# reentrancy lock
_reentrancy_lock: bool

# --- Dividend accounting per tokenId (single payment token model) ---
# magnifiedDividendPerShare[tokenId]
magnifiedDividendPerShare: public(HashMap[uint256, uint256])

# magnifiedDividendCorrections[tokenId][account] -> int256
magnifiedDividendCorrections: HashMap[uint256, HashMap[address, int256]]

# withdrawnDividends[tokenId][account] -> uint256
withdrawnDividends: HashMap[uint256, HashMap[address, uint256]]

# Mapping of Loan ID to the SHA-256 hash of the metadata
metadata_hash: public(HashMap[uint256, bytes32])    # loanId -> SHA-256 hash of metadata in bytes32

# ---- Loan Maturity ----
maturity: public(HashMap[uint256, uint64])   # tokenId -> unix timestamp


# --- Modifiers / internal checks ---
@internal
def _only_owner():
    assert msg.sender == self.owner, "only owner"

@internal
def _require_not_paused():
    assert not self.paused, "contract paused"

@internal
def _require_not_matured(_id: uint256):
    t: uint64 = self.maturity[_id]
    if t != 0:                       # 0 means "no maturity"
        assert block.timestamp < convert(t, uint256), "Token Matured"
 
@internal
def _set_fingerprint(loan_id: uint256, uri: String[256], fingerprint: bytes32):
    assert not self.exists[loan_id], "Loan ID already exists"
    self.tokenURI[loan_id] = uri
    self.metadata_hash[loan_id] = fingerprint

@internal
@view
def _get_fingerprint(loan_id: uint256) -> bytes32:
    return self.metadata_hash[loan_id]

# --- Constructor ---
@deploy
def __init__(_name: String[64], _symbol: String[32], _payment_token: address):
    """
    @notice Initializes the RWA Debt Engine.
    @param _name The legal name of the SPV/Contract.
    @param _symbol The ticker for the debt notes.
    @param _payment_token The USDC contract address on this chain.
    """
    assert _payment_token != ZERO, "no payment token"
    
    self.name = _name
    self.symbol = _symbol
    self.owner = msg.sender
    self.payment_token = _payment_token
    
    # Optional: If you want to use a Pausable feature, 
    # you would initialize it here.
    self.paused = False


# --- Owner control and maturity settings ---
@external
def pause():
    self._only_owner()
    self.paused = True
    log Paused(account=msg.sender)

@external
def unpause():
    self._only_owner()
    self.paused = False
    log Unpaused(account=msg.sender)

@external
def setMaturity(_id: uint256, _timestamp: uint64):
    """
    Set or update the maturity date for a token.
    Use 0 to remove maturity (perpetual).
    """
    self._only_owner()
    assert self.exists[_id], "Token ID does not exist"
    self.maturity[_id] = _timestamp
    log MaturitySet(tokenId=_id, maturityTime=_timestamp)


# --- ERC1155 view functions (some) ---
@external
@view
def balanceOf(_owner: address, _id: uint256) -> uint256:
    return self.balances[_owner][_id]

@external
@view
def get_fingerprint(loan_id: uint256) -> bytes32: 
    return self._get_fingerprint(loan_id)


@external
@view
def supportsInterface(interface_id: bytes32) -> bool:
    """
    @dev Standard ERC165 check. Tells other contracts/wallets 
    that this contract 'speaks' ERC1155.
    """
    for supported_id: bytes32 in SUPPORTED_INTERFACES:
        if interface_id == supported_id:
            return True
    return False

@external
@view
def balanceOfBatch(_owners: address[64], _ids: uint256[64]) -> uint256[64]:
    res: uint256[64] = empty(uint256[64])
    for i: uint256 in range(64): # Use literal or constant here
        if _owners[i] == ZERO:
            # We stop early if we hit a zero address to save execution gas
            break
        res[i] = self.balances[_owners[i]][_ids[i]]
    return res

@external
@view
def isApprovedForAll(_owner: address, _operator: address) -> bool:
    return self.operatorApproval[_owner][_operator]

@external
def setApprovalForAll(_operator: address, _approved: bool):
    assert _operator != msg.sender, "approve to caller"
    self.operatorApproval[msg.sender][_operator] = _approved
    log ApprovalForAll(owner=msg.sender, operator=_operator, approved=_approved)

# --- Internal safe transfer checks (ERC1155 receiver) ---
@internal
def _doSafeTransferAcceptanceCheck(
    _operator: address, 
    _from: address, 
    _to: address, 
    _id: uint256, 
    _value: uint256, 
    _data: Bytes[1024]
):
    if _to == ZERO:
        raise "ERC1155: transfer to zero"

    if _to.codesize > 0:
        selector: Bytes[4] = method_id("onERC1155Received(address,address,uint256,uint256,bytes)")
        
        payload: Bytes[196] = concat(
            selector,
            convert(_operator, bytes32),
            convert(_from, bytes32),
            convert(_id, bytes32),
            convert(_value, bytes32),
            convert(160, bytes32),
            convert(0, bytes32),
        )

        # FIX: We must declare both the success bool and the response bytes
        success: bool = False
        res: Bytes[32] = b""
        
        # We catch the tuple (bool, Bytes[32])
        success, res = raw_call(
            _to, 
            payload, 
            max_outsize=32, 
            is_static_call=True, 
            revert_on_failure=False
        )

        # 4. Validate the "Magic Value"
        # If the call failed (success == False) or the returned data is wrong
        if not success or len(res) < 4 or slice(res, 0, 4) != selector:
            raise "ERC1155: rejected by receiver"


# --- Internal transfer that updates dividend corrections ---
@internal
def _transfer_single(_operator: address, _from: address, _to: address, _id: uint256, _value: uint256):
    assert _to != ZERO, "transfer to zero"
    
    # RWA SAFETY: Optional - Prevent transfers of matured debt?
    self._require_not_matured(_id) 

    fromBal: uint256 = self.balances[_from][_id]
    assert fromBal >= _value, "insufficient balance"
    
    # State Updates
    self.balances[_from][_id] = fromBal - _value
    self.balances[_to][_id] += _value

    # Update magnified correction so dividends remain correct after transfer:
    # This prevents the new holder from claiming dividends that were earned 
    # BEFORE they owned the token.
    mag_per_share: uint256 = self.magnifiedDividendPerShare[_id]
    corr: int256 = convert(mag_per_share * _value, int256)
    
    self.magnifiedDividendCorrections[_id][_from] += corr
    self.magnifiedDividendCorrections[_id][_to] -= corr

    log TransferSingle(operator=_operator, from_=_from, to=_to, id=_id, value=_value)


# --- Safe single transfer ---
@external
@nonreentrant # external call in _doSafeTransferAcceptanceCheck
def safeTransferFrom(_from: address, _to: address, _id: uint256, _value: uint256, _data: Bytes[1024]=b""):
    operator: address = msg.sender
    # Authorization check
    assert _from == operator or self.operatorApproval[_from][operator], "Operation not Allowed"
    
    # Perform the state update
    self._transfer_single(operator, _from, _to, _id, _value)
    
    # Perform the safety check (External Call)
    self._doSafeTransferAcceptanceCheck(operator, _from, _to, _id, _value, _data)


# --- Owner token creation (create tokenId metadata + supply) ---
@external
def createToken(_id: uint256, _initialSupply: uint256, _price_in_usdc: uint256, _uri: String[256], fingerprint: bytes32):
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
    self._set_fingerprint(_id, _uri, fingerprint)

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

# Owner can transfer ownership
@external
def transferOwnership(_newOwner: address):
    self._only_owner()
    assert _newOwner != ZERO, "New owner is zero address"
    old_owner: address = self.owner
    self.owner = _newOwner
    log OwnershipTransferred(previousOwner=old_owner, newOwner=_newOwner)


# --- Buy function: buyer must approve USDC to this contract first ---
@external
@nonreentrant
def buy(_id: uint256, _units: uint256):
    """Primary issuance logic with global reentrancy lock."""
    self._require_not_paused()
    self._require_not_matured(_id)
    assert self.exists[_id], "Token ID does not exist"
    assert _units > 0, "Units must be greater than zero"
    
    price: uint256 = self.tokenPriceUSD[_id] * _units
    # safe_erc20_transferFrom is a push-pull mechanism
    assert self._safe_erc20_transferFrom(self.payment_token, msg.sender, self, price), "USDC transfer failed"

    self.tokenSupply[_id] += _units
    self.balances[msg.sender][_id] += _units
    
    # Update dividend corrections to prevent "double-claiming" historical interest
    corr: int256 = convert(self.magnifiedDividendPerShare[_id] * _units, int256)
    self.magnifiedDividendCorrections[_id][msg.sender] -= corr

    log TransferSingle(operator=msg.sender, from_=ZERO, to=msg.sender, id=_id, value=_units)

    
# --- Dividend deposit (owner or approved payer) ---
@external
@nonreentrant
def depositDividends(_id: uint256, _amount: uint256):
    self._require_not_paused()
    assert self.exists[_id], "Token ID does not exist"
    
    # Check supply BEFORE taking the money
    supply: uint256 = self.tokenSupply[_id]
    
    # INSTITUTIONAL LOGIC: 
    # If nobody owns the debt, we shouldn't take the dividend. 
    # This protects the SPV from "losing" cash in the contract.
    assert supply > 0, "No active holders to receive funds" 
    assert _amount > 0, "Amount must be > 0"
    
    # Now pull the USDC
    assert self._safe_erc20_transferFrom(self.payment_token, msg.sender, self, _amount), "USDC deposit failed"

    # Update the global ratio
    # MAGNITUDE (10**24) ensures your $1 testing works perfectly
    increment: uint256 = (_amount * MAGNITUDE) // supply
    self.magnifiedDividendPerShare[_id] += increment

    log DividendsDeposited(
        depositor=msg.sender, 
        tokenId=_id, 
        amount=_amount, 
        magnifiedDividendPerShare=self.magnifiedDividendPerShare[_id]
    )
    
@internal
@view
def _accumulativeDividendOf(_id: uint256, _account: address) -> uint256:
    mag_share: uint256 = self.magnifiedDividendPerShare[_id]
    bal: uint256 = self.balances[_account][_id]
    
    if bal == 0:
        return 0

    # 1. Calculate the total magnified earnings (Share * Balance)
    # Use uint256 for the high-precision product
    magnified_earnings: uint256 = mag_share * bal
    
    # 2. Add/Subtract the correction while still in "Magnified" state
    corr_signed: int256 = self.magnifiedDividendCorrections[_id][_account]
    
    # We convert magnified_earnings to int256 to do math with the correction
    total_magnified_after_corr: int256 = convert(magnified_earnings, int256) + corr_signed
    
    # 3. If the result is negative (shouldn't happen with correct logic), return 0
    if total_magnified_after_corr <= 0:
        return 0
    
    # 4. FINALLY divide by MAGNITUDE to get the actual USDC amount
    # This keeps all your "cents" and "dust" precision intact
    return convert(total_magnified_after_corr, uint256) // MAGNITUDE

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


# --- Emergency owner withdraw (use with caution) ---
@external
@nonreentrant
def emergencyWithdrawERC20(_to: address, _amount: uint256):
    """SPV Safety function to rescue funds."""
    self._only_owner()
    payload: Bytes[68] = concat(
        method_id("transfer(address,uint256)"), 
        convert(_to, bytes32), 
        convert(_amount, bytes32)
    )
    
    # FIX: Remove the ", _" and the comma. 
    # Since max_outsize=0, raw_call only returns the success boolean.
    ok: bool = raw_call(self.payment_token, payload, max_outsize=0, revert_on_failure=False)
    assert ok, "Rescue transfer failed"

# --- Admin: change price & uri ---
@external
def setTokenPrice(_id: uint256, _price: uint256):
    self._only_owner()
    assert self.exists[_id], "id not exists"
    self.tokenPriceUSD[_id] = _price


@external
def set_loan_terms(loan_id: uint256, uri: String[256], fingerprint: bytes32):
    self._only_owner()
    self.tokenURI[loan_id] = uri
    self.metadata_hash[loan_id] = fingerprint
    log URI(value=uri, id=loan_id)


@internal
def _safe_erc20_transfer(_token: address, _to: address, _amount: uint256) -> bool:
    """
    @notice Pushes USDC from this contract to a recipient.
    @dev SECURITY: Functions calling this MUST use @nonreentrant.
    @dev Low-level 'Safe' wrapper for ERC20 transfer(). 
    Handles 'The USDT Problem': Some tokens don't return a boolean. 
    1. If the call reverts -> returns False.
    2. If the call returns nothing -> assumes success (True).
    3. If the call returns a value -> checks if that value is non-zero (True).
    """
    # 1. Construct the ERC20 'transfer(address,uint256)' payload
    payload: Bytes[68] = concat(
        method_id("transfer(address,uint256)"), 
        convert(_to, bytes32), 
        convert(_amount, bytes32)
    )
    
    # 2. Execute the raw call
    # max_outsize=32 allows us to capture the Boolean return if it exists
    ok: bool = False
    ret: Bytes[32] = b""
    ok, ret = raw_call(_token, payload, max_outsize=32, revert_on_failure=False)
    
    # 3. Security Check: The "Double-Green" Logic
    if not ok:
        return False # The call itself failed (out of gas, revert, etc.)
    
    if len(ret) == 0:
        # Case A: Non-standard tokens (like USDT on some chains) that return nothing.
        # If the call didn't revert, we assume success.
        return True
        
    # Case B: Standard tokens (like USDC) that return a boolean.
    # We convert the 32-byte return buffer to a uint256. 0 is False, anything else is True.
    return convert(ret, uint256) != 0

@internal
def _safe_erc20_transferFrom(_token: address, _from: address, _to: address, _amount: uint256) -> bool:
    """
    @notice Pulls USDC from an investor's wallet into this contract.
    @dev SECURITY: Functions calling this MUST use @nonreentrant.
    - Handles 'The Pull Problem': Moves tokens from '_from' to '_to' using an allowance.
    - Checks for both standard (bool) and non-standard (empty) return data to prevent false-negative failures on older token contracts.
    """
    payload: Bytes[100] = concat(
        method_id("transferFrom(address,address,uint256)"), 
        convert(_from, bytes32), 
        convert(_to, bytes32), 
        convert(_amount, bytes32)
    )
    ok: bool = False
    ret: Bytes[32] = b""
    ok, ret = raw_call(_token, payload, max_outsize=32, revert_on_failure=False)
    # Success if it returns 'true' OR nothing (standard non-compliant tokens)
    return ok and (len(ret) == 0 or convert(ret, uint256) != 0)

