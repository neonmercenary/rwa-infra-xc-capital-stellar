# @version ^0.4.0

"""
RWALite.vy (Tranched Version)
Supports "The Crazy Model":
- Parent IDs link to Senior/Junior sub-tokens.
- Payout Caps define the waterfall (e.g., Senior capped at -5% if yield >= 15%, -3% if yield > 10% < 15% and -1% if yield < 10%).
- Buy/Secondary disabled for MVP sanity.

"""

from ethereum.ercs import IERC20

# --- Events ---
event TokenCreated:
    id: indexed(uint256)
    initialSupply: uint256
    priceUSDC: uint256
    uri: String[256]
    fingerprint: bytes32

event TrancheLoanLinked:
    parentId: indexed(uint256)
    seniorId: uint256
    juniorId: uint256

event TransferSingle:
    operator: indexed(address)
    from_: indexed(address)
    to: indexed(address)
    id: uint256
    value: uint256

event DividendsDeposited:
    depositor: indexed(address)
    tokenId: uint256
    amount: uint256
    magnifiedDividendPerShare: uint256

event MaturitySet:
    tokenId: indexed(uint256)
    maturityTime: uint64

event OwnershipTransferred:
    previousOwner: indexed(address)
    newOwner: indexed(address)

event URI:
    value: String[256]
    id: indexed(uint256)

# --- Constants ---
MAGNITUDE: constant(uint256) = 10 ** 24
ZERO: constant(address) = empty(address)

# --- Storage ---
name: public(String[64])
symbol: public(String[32])
payment_token: public(address)
owner: public(address)
paused: public(bool)

# ERC1155-like storage
balances: HashMap[address, HashMap[uint256, uint256]]
tokenSupply: public(HashMap[uint256, uint256])
tokenPriceUSD: public(HashMap[uint256, uint256])
tokenURI: public(HashMap[uint256, String[256]])
exists: public(HashMap[uint256, bool])
metadata_hash: public(HashMap[uint256, bytes32])
maturity: public(HashMap[uint256, uint64])
isFinalized: public(HashMap[uint256, bool])

# --- NEW: Tranche & Waterfall Storage ---
# parentID -> [SeniorID, JuniorID]
tranches: public(HashMap[uint256, uint256[2]])

# tokenId -> Max payout per slice (Principal + Fixed Interest)
# If 0, it is considered uncapped (Junior/Equity)
payoutCapPerSlice: public(HashMap[uint256, uint256])

# --- Dividend accounting ---
magnifiedDividendPerShare: public(HashMap[uint256, uint256])
magnifiedDividendCorrections: HashMap[uint256, HashMap[address, int256]]

# Reentrancy lock
_reentrancy_lock: bool

# --- Modifiers ---
@internal
def _only_owner():
    assert msg.sender == self.owner, "only owner"

@internal
def _require_not_paused():
    assert not self.paused, "contract paused"

# --- Constructor ---
@deploy
def __init__(_name: String[64], _symbol: String[32], _payment_token: address):
    assert _payment_token != ZERO, "no payment token"
    self.name = _name
    self.symbol = _symbol
    self.owner = msg.sender
    self.payment_token = _payment_token

# --- NEW: Create Tranche Loan ---
@external
def createTrancheLoan(
    _parentId: uint256,
    _seniorId: uint256,
    _juniorId: uint256,
    _seniorSupply: uint256,
    _juniorSupply: uint256,
    _seniorPrice: uint256,
    _juniorPrice: uint256,
    _seniorCap: uint256,
    _uri: String[256],
    _fingerprint: bytes32
):
    """
    @notice Creates a linked Senior/Junior tranche pair under a Parent Loan.
    @param _seniorCap The max payout (Principal + 8% etc) per slice in 6 decimals.
    """
    self._only_owner()
    assert not self.exists[_seniorId] and not self.exists[_juniorId], "IDs exist"

    # Link Tranches
    self.tranches[_parentId] = [_seniorId, _juniorId]
    self.payoutCapPerSlice[_seniorId] = _seniorCap # e.g. 102.60 * 10^6
    
    # Initialize Senior
    self.exists[_seniorId] = True
    self.tokenSupply[_seniorId] = _seniorSupply
    self.tokenPriceUSD[_seniorId] = _seniorPrice
    self.tokenURI[_seniorId] = _uri
    
    # Initialize Junior
    self.exists[_juniorId] = True
    self.tokenSupply[_juniorId] = _juniorSupply
    self.tokenPriceUSD[_juniorId] = _juniorPrice
    self.tokenURI[_juniorId] = _uri
    
    # Mint to SPV (Owner) initially
    self.balances[self.owner][_seniorId] = _seniorSupply
    self.balances[self.owner][_juniorId] = _juniorSupply

    log TrancheLoanLinked(parentId=_parentId, seniorId=_seniorId, juniorId=_juniorId)
    log TokenCreated(id=_seniorId, initialSupply=_seniorSupply, priceUSDC=_seniorPrice, uri=_uri, fingerprint=_fingerprint)
    log TokenCreated(id=_juniorId, initialSupply=_juniorSupply, priceUSDC=_juniorPrice, uri=_uri, fingerprint=_fingerprint)

# --- Safe single transfer (LOCKED FOR MVP) ---
@external
def safeTransferFrom(_from: address, _to: address, _id: uint256, _value: uint256, _data: Bytes[1024]=b""):
    """
    @dev Restricted to Owner (SPV) only for sanity. Investors cannot trade.
    """
    assert msg.sender == self.owner, "Secondary trading disabled"
    
    fromBal: uint256 = self.balances[_from][_id]
    assert fromBal >= _value, "insufficient balance"
    
    self.balances[_from][_id] = fromBal - _value
    self.balances[_to][_id] += _value

    # Correction logic
    mag_per_share: uint256 = self.magnifiedDividendPerShare[_id]
    corr: int256 = convert(mag_per_share * _value, int256)
    self.magnifiedDividendCorrections[_id][_from] += corr
    self.magnifiedDividendCorrections[_id][_to] -= corr

    log TransferSingle(operator=msg.sender, from_=_from, to=_to, id=_id, value=_value)

# --- Dividend Payout ---
@external
@nonreentrant
def depositDividends(_id: uint256, _amount: uint256):
    self._require_not_paused()
    assert self.exists[_id], "Token ID does not exist"
    assert not self.isFinalized[_id], "Loan finalized"
    
    supply: uint256 = self.tokenSupply[_id]
    assert supply > 0, "No holders"
    
    # Pull USDC
    payload: Bytes[100] = concat(
        method_id("transferFrom(address,address,uint256)"), 
        convert(msg.sender, bytes32), 
        convert(self, bytes32), 
        convert(_amount, bytes32)
    )
    ok: bool = False
    ret: Bytes[32] = b""
    ok, ret = raw_call(self.payment_token, payload, max_outsize=32, revert_on_failure=False)
    assert ok and (len(ret) == 0 or convert(ret, uint256) != 0), "USDC Transfer Failed"

    # Update Ratio
    increment: uint256 = (_amount * MAGNITUDE) // supply
    self.magnifiedDividendPerShare[_id] += increment

    log DividendsDeposited(depositor=msg.sender, tokenId=_id, amount=_amount, magnifiedDividendPerShare=self.magnifiedDividendPerShare[_id])

@external
def finalizeLoanBatch(_id: uint256, _investors: address[100]):
    """
    @dev Call this from Python in batches of 100. Wipes balances and updates supply.
    """
    self._only_owner()
    mag_per_share: uint256 = self.magnifiedDividendPerShare[_id]

    for investor: address in _investors:
        if investor == ZERO:
            break
            
        amount: uint256 = self.balances[investor][_id]
        if amount > 0:
            corr: int256 = convert(mag_per_share * amount, int256)
            self.magnifiedDividendCorrections[_id][investor] += corr
            self.balances[investor][_id] = 0
            self.tokenSupply[_id] -= amount
            log TransferSingle(operator=msg.sender, from_=investor, to=ZERO, id=_id, value=amount)

    if self.tokenSupply[_id] == 0:
        self.isFinalized[_id] = True

# --- View Helper ---
@external
@view
def withdrawableDividendOf(_id: uint256, _account: address) -> uint256:
    mag_share: uint256 = self.magnifiedDividendPerShare[_id]
    bal: uint256 = self.balances[_account][_id]
    if bal == 0: return 0
    
    mag_earnings: uint256 = mag_share * bal
    corr: int256 = self.magnifiedDividendCorrections[_id][_account]
    
    total: int256 = convert(mag_earnings, int256) + corr
    if total <= 0: return 0
    return convert(total, uint256) // MAGNITUDE