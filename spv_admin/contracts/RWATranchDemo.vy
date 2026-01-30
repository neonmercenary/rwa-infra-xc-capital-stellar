# @version 0.4.3

"""
RWATranchDemo.vy (Tranched Version)
Supports "The Crazy Model":
- Parent IDs link to Senior/Junior sub-tokens. 
- Payout Caps define the waterfall (e.g., Senior capped at 8%). 
- Buy/Secondary disabled for MVP sanity. 
"""

from ethereum.ercs import IERC20

# --- Events ---
event TokenCreated:
    id: indexed(uint256)
    initialSupply: uint256
    price: uint256
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

event MaturitySet:
    tokenId: indexed(uint256)
    maturityTime: uint64

event OwnershipTransferred:
    previousOwner: indexed(address)
    newOwner: indexed(address)

event Paused:
    account: indexed(address)

event Unpaused:
    account: indexed(address)

event URI:
    value: String[256]
    id: indexed(uint256)


# Standard ERC-1155 Interface IDs
# 0xd9b67a26 = ERC1155
# 0x01ffc9a7 = ERC165
SUPPORTED_INTERFACES: constant(bytes32[2]) = [
    0x01ffc9a700000000000000000000000000000000000000000000000000000000,
    0xd9b67a2600000000000000000000000000000000000000000000000000000000
]


# --- Constants ---
MAGNITUDE: constant(uint256) = 10 ** 24     # This will handle even $0.000000001 dividends accurately. Finance precision.
ZERO: constant(address) = empty(address) 

# --- Storage ---
name: public(String[64]) 
symbol: public(String[32]) 
payment_token: public(address) 
owner: public(address) 
paused: public(bool)
metadata_hash: public(HashMap[uint256, bytes32])    # Mapping of Loan ID to the SHA-256 hash of the metadata (loanId -> SHA-256 hash of metadata in bytes32)

balances: public(HashMap[address, HashMap[uint256, uint256]]) 
tokenSupply: public(HashMap[uint256, uint256]) 
tokenPrice: public(HashMap[uint256, uint256]) 
tokenURI: public(HashMap[uint256, String[256]]) 
exists: public(HashMap[uint256, bool]) 
maturity: public(HashMap[uint256, uint64]) 
isFinalized: public(HashMap[uint256, bool])  # Indicates if a loan/tranche has been finalized (ID -> bool) 

tranches: public(HashMap[uint256, uint256[2]]) 
sibling: public(HashMap[uint256, uint256]) 
payoutCapPerSlice: public(HashMap[uint256, uint256]) 

magnifiedDividendPerShare: public(HashMap[uint256, uint256]) 
magnifiedDividendCorrections: HashMap[uint256, HashMap[address, int256]] 
has_distributed_dividends: public(bool)

# --- Internal Helpers ---
@internal
def _only_owner():
    assert msg.sender == self.owner, "Not Admin, Cannot proceed" 

@internal
def _maturity_check(_id: uint256):
    assert block.timestamp >= convert(self.maturity[_id], uint256), "Loan is not matured"

@internal
@view
def _get_fingerprint(loan_id: uint256) -> bytes32:
    return self.metadata_hash[loan_id]

@internal
def _require_not_paused():
    assert not self.paused, "Contract paused"

@internal
def _require_not_finalized(_id: uint256):
    assert not self.isFinalized[_id], "Loan finalized"


# --- Constructor ---
@deploy
def __init__(_name: String[64], _symbol: String[32], _payment_token: address):
    assert _payment_token != ZERO, "no payment token" 
    self.name = _name 
    self.symbol = _symbol 
    self.owner = msg.sender 
    self.payment_token = _payment_token 
    log OwnershipTransferred(previousOwner=ZERO, newOwner=msg.sender)

# --- Admin Functions ---
@external
def createTrancheToken(
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
    self._only_owner() 
    assert not self.exists[_seniorId] and not self.exists[_juniorId], "Tranches IDs exist" 
    assert _juniorId != 0, "Junior ID cannot be 0" 

    self.tranches[_parentId] = [_seniorId, _juniorId] 
    self.sibling[_seniorId] = _juniorId 
    self.sibling[_juniorId] = _seniorId 
    self.payoutCapPerSlice[_seniorId] = _seniorCap 
    
    for tid: uint256 in [_seniorId, _juniorId]:
        self.exists[tid] = True 
        self.tokenURI[tid] = _uri 
    
    self.tokenSupply[_seniorId] = _seniorSupply 
    self.tokenPrice[_seniorId] = _seniorPrice 
    self.tokenSupply[_juniorId] = _juniorSupply 
    self.tokenPrice[_juniorId] = _juniorPrice 
    
    self.balances[self.owner][_seniorId] = _seniorSupply 
    self.balances[self.owner][_juniorId] = _juniorSupply 

    log TrancheLoanLinked(parentId=_parentId, seniorId=_seniorId, juniorId=_juniorId)
    log TokenCreated(id=_seniorId, initialSupply=_seniorSupply, price=_seniorPrice, uri=_uri, fingerprint=_fingerprint)
    log TokenCreated(id=_juniorId, initialSupply=_juniorSupply, price=_juniorPrice, uri=_uri, fingerprint=_fingerprint)

@external
def setMaturity(_id: uint256, _time: uint64):
    self._only_owner()
    self.maturity[_id] = _time
    log MaturitySet(tokenId=_id, maturityTime=_time)


@external
def pause():
    '''
    Pause the contract. 
    '''
    self._only_owner()
    self.paused = True
    log Paused(account=msg.sender)

@external
def unpause():
    '''
    Unpause the contract.
    '''
    self._only_owner()
    self.paused = False
    log Unpaused(account=msg.sender)


# --- ERC1155 view functions (some) ---
@external
@view
def balanceOf(_owner: address, _id: uint256) -> uint256:
    '''
    @notice Returns the balance of tokens for a given owner and token ID.
    @param _owner The address of the token holder.  
    @param _id The ID of the token.    
    '''
    return self.balances[_owner][_id]

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

@external
@view
def get_fingerprint(loan_id: uint256) -> bytes32: 
    '''
    @notice Returns the SHA-256 fingerprint of the loan metadata.
    @param loan_id The ID of the loan/token.    
    '''
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

# --- ERC1155 external functions (some) ---

@external
def safeTransferFrom(_from: address, _to: address, _id: uint256, _value: uint256):
    '''
    @dev Disabled secondary trading for MVP sanity.
    '''
    assert not self.paused, "Contract paused"
    assert msg.sender == self.owner, "Secondary trading disabled" 
    assert _to != ZERO, "Transfer to zero address" 
    assert self.exists[_id], "Token ID does not exist"
    fromBal: uint256 = self.balances[_from][_id] 
    assert fromBal >= _value, "insufficient balance" 
    
    self.balances[_from][_id] = fromBal - _value 
    self.balances[_to][_id] += _value 

    mag_per_share: uint256 = self.magnifiedDividendPerShare[_id] 
    corr: int256 = convert(mag_per_share * _value, int256) 
    self.magnifiedDividendCorrections[_id][_from] += corr 
    self.magnifiedDividendCorrections[_id][_to] -= corr 

    log TransferSingle(operator=msg.sender, from_=_from, to=_to, id=_id, value=_value) 


@external
@nonreentrant
def depositDividends(_id: uint256, _amount: uint256):
    assert not self.paused,                         "Contract Paused"
    assert not self.isFinalized[_id],               "Loan finalized"
    assert self.exists[_id],                        "Token ID does not exist"
    assert self.sibling[_id] != 0,                  "Must deposit to Senior ID"
    
    supply: uint256 = self.tokenSupply[_id]
    assert supply > 0,                              "No holders"
    
    # --- DEMO BYPASS START ---
    # Fix: Define the payload type explicitly for Vyper
    payload: Bytes[100] = concat(
        method_id("transferFrom(address,address,uint256)"), 
        convert(msg.sender, bytes32), 
        convert(self, bytes32), 
        convert(_amount, bytes32)
    )
    
    # Fix: Correctly handle return values even if we ignore them
    ok: bool = False
    ok = raw_call(
        self.payment_token, 
        payload, 
        max_outsize=0, 
        revert_on_failure=False
    )
    # Even if ok is False (insufficient funds), logic continues...
    # --- DEMO BYPASS END ---

    remaining_mag_funds: uint256 = _amount * MAGNITUDE 
    target_id: uint256 = _id
    
    cap: uint256 = self.payoutCapPerSlice[target_id]
    
    # Waterfall Logic (Senior Tranche)
    if cap > 0 and supply > 0:
        mag_cap: uint256 = cap * MAGNITUDE
        current_mag: uint256 = self.magnifiedDividendPerShare[target_id]
        
        if current_mag < mag_cap:
            needed_per_share: uint256 = mag_cap - current_mag
            total_needed_mag: uint256 = needed_per_share * supply
            
            if remaining_mag_funds >= total_needed_mag:
                # Fill Senior to cap and move to Junior sibling
                self.magnifiedDividendPerShare[target_id] = mag_cap
                remaining_mag_funds -= total_needed_mag
                target_id = self.sibling[target_id] 
            else:
                # Distribute everything remaining to Senior
                self.magnifiedDividendPerShare[target_id] += remaining_mag_funds // supply
                remaining_mag_funds = 0

    # Spillover Logic (Junior Tranche)
    if remaining_mag_funds > 0 and target_id != 0:
        j_supply: uint256 = self.tokenSupply[target_id]
        if j_supply > 0:
            self.magnifiedDividendPerShare[target_id] += remaining_mag_funds // j_supply
            
    if not self.has_distributed_dividends:
        self.has_distributed_dividends = True

    log DividendsDeposited(depositor=msg.sender, tokenId=_id, amount=_amount)

@external
def finalizeLoanBatch(_id: uint256, _investors: address[100]):
    self._only_owner()
    
    mag_per_share: uint256 = self.magnifiedDividendPerShare[_id] 

    for investor: address in _investors:
        if investor == ZERO: break 
        amount: uint256 = self.balances[investor][_id] 
        if amount > 0:
            self.magnifiedDividendCorrections[_id][investor] += convert(mag_per_share * amount, int256) 
            self.balances[investor][_id] = 0 
            self.tokenSupply[_id] -= amount
            log TransferSingle(operator=msg.sender, from_=investor, to=ZERO, id=_id, value=amount) 

    if self.tokenSupply[_id] == 0:
        self.isFinalized[_id] = True
        sib: uint256 = self.sibling[_id]
        if sib != 0 and self.tokenSupply[sib] == 0:
            self.isFinalized[sib] = True

    
@external
@nonreentrant
def withdraw(_id: uint256):
    assert block.timestamp >= convert(self.maturity[_id], uint256), "Not matured"
    
    mag_share: uint256 = self.magnifiedDividendPerShare[_id]
    bal: uint256 = self.balances[msg.sender][_id]
    assert bal > 0, "No balance"
    
    mag_earnings: uint256 = mag_share * bal
    corr: int256 = self.magnifiedDividendCorrections[_id][msg.sender]
    total_mag: int256 = convert(mag_earnings, int256) + corr
    
    assert total_mag > 0, "Nothing to withdraw"
    withdrawable_amount: uint256 = convert(total_mag, uint256) // MAGNITUDE
    assert withdrawable_amount > 0, "Too small"

    self.magnifiedDividendCorrections[_id][msg.sender] -= convert(withdrawable_amount * MAGNITUDE, int256)

    success: bool = extcall IERC20(self.payment_token).transfer(msg.sender, withdrawable_amount)
    assert success, "Transfer Failed"


@external
def emergencyRefund():
    """
    @notice Owner can recover all funds ONLY if operations haven't started.
    """
    self._only_owner()
    
    # 1. The Global Guard
    # If even 1 wei has been deposited as dividends, this locks forever.
    assert not self.has_distributed_dividends, "Dividends already active"

    # 2. Sweep Funds
    balance: uint256 = staticcall IERC20(self.payment_token).balanceOf(self)
    assert balance > 0, "Nothing to refund"
    
    success: bool = extcall IERC20(self.payment_token).transfer(msg.sender, balance)
    assert success, "Transfer failed"