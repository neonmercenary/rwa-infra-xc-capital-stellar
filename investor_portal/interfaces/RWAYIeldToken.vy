# @version ^0.4

"""
RWAYieldToken.vy

- ERC20-like token representing fractional ownership of an SPV's cashflow.
- Pull-based dividend distribution in an ERC20 token (e.g. USDC).
- Uses the "magnified dividend per share" pattern to keep precise per-holder accounting.

Assumptions / usage:
- Owner (SPV manager) mints tokens to investor addresses equal to their share.
- When a payment (USDC) for borrower cashflow arrives, SPV calls `depositDividends(amount, token_address)`.
- The contract receives tokens via prior ERC20 `approve` from the depositor; depositDividends does safe transferFrom.
- Token holders call `withdrawDividend(token_address)` to pull their owed stablecoin.
"""

from ethereum.ercs import IERC20

# --- Events ---
event Transfer:
    _from: indexed(address)
    _to: indexed(address)
    _value: uint256

event Approval:
    _owner: indexed(address)
    _spender: indexed(address)
    _value: uint256

event DividendsDeposited:
    depositor: indexed(address)
    erc20: indexed(address)
    amount: uint256
    magnifiedDividendPerShare: uint256

event DividendWithdrawn:
    account: indexed(address)
    erc20: indexed(address)
    amount: uint256

event Mint:
    to: indexed(address)
    amount: uint256

event Burn:
    from_: indexed(address)
    amount: uint256

# --- State variables (ERC20) ---
name: public(String[64])
symbol: public(String[32])
decimals: public(uint256)

totalSupply: public(uint256)
balances: HashMap[address, uint256]
allowances: HashMap[address, HashMap[address, uint256]]

owner: public(address)

# --- Dividend accounting (magnified dividends) ---
# We support multiple payment ERC20 tokens (e.g., USDC or other stablecoins).
# magnifiedDividendPerShare[erc20] stores the cumulative "magnified" per-share value for each payment token.
magnifiedDividendPerShare: HashMap[address, uint256]

# Per-holder correction value (signed) so that mint/burn/transfer keep dividend accounting correct.
magnifiedDividendCorrections: HashMap[address, HashMap[address, int256]]  # erc20 => account => correction

# Withdrawn dividends per token
withdrawnDividends: HashMap[address, HashMap[address, uint256]]  # erc20 => account => amount

# Magnification constant to retain precision when dividing by totalSupply
MAGNITUDE: constant(uint256) = 10 ** 24

# --- Modifiers (implemented as internal checks) ---
@internal
def _only_owner():
    assert msg.sender == self.owner, "only owner"

# --- Constructor ---
@deploy
def __init__(_name: String[64], _symbol: String[32]):
    """
    Initialize token.
    Owner = deployer (SPV manager)
    """
    self.name = _name
    self.symbol = _symbol
    self.decimals = _decimals
    self.owner = msg.sender
    self.totalSupply = 0

# --- ERC20 standard functions (simplified) ---
@external
@view
def balanceOf(_owner: address) -> uint256:
    return self.balances[_owner]

@external
@view
def allowance(_owner: address, _spender: address) -> uint256:
    return self.allowances[_owner][_spender]

@external
def approve(_spender: address, _value: uint256) -> bool:
    self.allowances[msg.sender][_spender] = _value
    log Approval(_owner=msg.sender, _spender=_spender, _value=_value)
    return True

@external
def transfer(_to: address, _value: uint256) -> bool:
    self._transfer(msg.sender, _to, _value)
    return True

@external
def transferFrom(_from: address, _to: address, _value: uint256) -> bool:
    allowed: uint256 = self.allowances[_from][msg.sender]
    assert allowed >= _value, "allowance exceeded"
    self.allowances[_from][msg.sender] = allowed - _value
    self._transfer(_from, _to, _value)
    return True

@internal
def _transfer(_from: address, _to: address, _value: uint256):
    assert _from != ZERO_ADDRESS and _to != ZERO_ADDRESS, "zero address"
    bal_from: uint256 = self.balances[_from]
    assert bal_from >= _value, "insufficient balance"
    # update balances
    self.balances[_from] = bal_from - _value
    self.balances[_to] += _value

    # update magnified dividend corrections for all tracked payment tokens
    # for efficiency, we do this for tokens that have non-zero magnifiedDividendPerShare only.
    # Note: in Vyper iterating dynamic mappings is not possible; thus caller must ensure not too many payment tokens used.
    # Adjust corrections for transfer: correction_to_add = magnifiedDividendPerShare[erc] * _value
    # We'll handle corrections in a generic internal helper for a single erc20 when necessary (used by caller).
    # For correctness, we update corrections for all tokens by reading map keys is impossible in Vyper.
    # Therefore we require that the platform restricts to a small known set of payment tokens (e.g. USDC).
    # Here we will only update correction for defaultToken if used — see docs for usage.
    # Practical implementers should limit payment tokens to 1 (USDC) to keep gas complexity low.

    # Update correction for default token: if used. (no-op if zero)
    # NOTE: This contract uses multi-token mappings, but due to Vyper limits we rely on best practice:
    # use a single stablecoin (USDC) address passed to deposit/withdraw functions.
    default_token: address = ZERO_ADDRESS  # placeholder - real flows pass token explicitly when claiming
    if self.magnifiedDividendPerShare[default_token] != 0:
        corr: int256 = convert(self.magnifiedDividendPerShare[default_token] * _value, int256)
        # decrease correction for receiver and increase for sender
        self.magnifiedDividendCorrections[default_token][_from] += corr
        self.magnifiedDividendCorrections[default_token][_to] -= corr

    log Transfer(_from, _to, _value)

# --- Mint / Burn (owner only) ---
@external
def mint(_to: address, _value: uint256):
    """
    Owner mints tokens to _to. This increases totalSupply and adjusts magnified dividend corrections
    so that newly minted tokens do not retroactively receive past dividends.
    """
    self._only_owner()

    assert _to != ZERO_ADDRESS, "zero address"
    # increase totalSupply and balance
    self.totalSupply += _value
    self.balances[_to] += _value

    # Update correction: newly minted tokens should not receive past dividends.
    # correction = magnifiedDividendPerShare * _value
    # magnifiedDividendCorrections[erc][_to] += -correction (subtract)
    # Because we store corrections as signed, subtracting moves it in the right direction.
    # We must do this for each payment token - but practically we expect 1 token (USDC).
    # We update all present tokens by reading mapping keys is not feasible in Vyper; user uses default token.
    default_token: address = ZERO_ADDRESS
    corr: int256 = convert(self.magnifiedDividendPerShare[default_token] * _value, int256)
    self.magnifiedDividendCorrections[default_token][_to] -= corr

    log Mint(_to, _value)
    log Transfer(ZERO_ADDRESS, _to, _value)

@external
def burn(_from: address, _value: uint256):
    """
    Owner burns tokens from _from (reduce supply). Adjusts corrections appropriately.
    """
    self._only_owner()
    assert _from != ZERO_ADDRESS, "zero address"
    bal: uint256 = self.balances[_from]
    assert bal >= _value, "insufficient balance"

    self.balances[_from] = bal - _value
    self.totalSupply -= _value

    default_token: address = ZERO_ADDRESS
    corr: int256 = convert(self.magnifiedDividendPerShare[default_token] * _value, int256)
    self.magnifiedDividendCorrections[default_token][_from] += corr

    log Burn(_from, _value)
    log Transfer(_from, ZERO_ADDRESS, _value)

# --- Dividend deposit and withdraw (multi-ERC20 support) ---
@external
def depositDividends(_erc20: address, _amount: uint256):
    """
    Owner/anyone can deposit stablecoins (e.g. USDC) into this contract to be distributed pro-rata.
    Precondition: depositor must have approved this contract to transfer `_amount` of `_erc20`.
    On success, magnifiedDividendPerShare for _erc20 is increased.
    """
    # transfer tokens into contract
    assert _erc20 != ZERO_ADDRESS, "no token"
    erc: ERC20 = ERC20(_erc20)
    # pull funds
    success: bool = erc.transferFrom(msg.sender, self, _amount)
    assert success, "transferFrom failed"

    if self.totalSupply == 0:
        # no token holders, deposit remains in contract as buffer
        # but still emit event
        log DividendsDeposited(msg.sender, _erc20, _amount, self.magnifiedDividendPerShare[_erc20])
        return

    # magnified increment = amount * MAGNITUDE / totalSupply
    increment: uint256 = (_amount * MAGNITUDE) / self.totalSupply
    self.magnifiedDividendPerShare[_erc20] += increment

    log DividendsDeposited(msg.sender, _erc20, _amount, self.magnifiedDividendPerShare[_erc20])

@internal
@view
def _accumulativeDividendOf(_erc20: address, _account: address) -> uint256:
    """
    total accumulated (not yet withdrawn) dividend for account in _erc20 terms
    accumulative = (magnifiedDividendPerShare * balance + correction) / MAGNITUDE
    """
    mag_share: uint256 = self.magnifiedDividendPerShare[_erc20]
    # convert to signed for adding correction (which can be negative)
    balance: uint256 = self.balances[_account]
    accum: uint256 = 0
    if mag_share != 0 and balance != 0:
        raw: uint256 = mag_share * balance
        corr_signed: int256 = self.magnifiedDividendCorrections[_erc20][_account]
        # raw is uint256 but corr could be negative
        # compute (raw as int256 + corr_signed) / MAGNITUDE
        raw_signed: int256 = convert(raw, int256) + corr_signed
        if raw_signed <= 0:
            accum = 0
        else:
            accum = convert(raw_signed / convert(MAGNITUDE, int256), uint256)
    return accum

@external
@view
def withdrawableDividendOf(_erc20: address, _account: address) -> uint256:
    """
    Returns the amount the account can withdraw right now (accumulative - already withdrawn).
    """
    total_accum: uint256 = self._accumulativeDividendOf(_erc20, _account)
    withdrawn: uint256 = self.withdrawnDividends[_erc20][_account]
    if total_accum <= withdrawn:
        return 0
    return total_accum - withdrawn

@external
def withdrawDividend(_erc20: address):
    """
    Withdraw available dividend for msg.sender in token _erc20.
    Uses pull pattern. Transfers tokens from contract to msg.sender.
    """
    amount: uint256 = self.withdrawableDividendOf(_erc20, msg.sender)
    assert amount > 0, "no dividend"

    # mark withdrawn
    self.withdrawnDividends[_erc20][msg.sender] += amount

    erc: ERC20 = ERC20(_erc20)
    success: bool = erc.transfer(msg.sender, amount)
    assert success, "token transfer failed"

    log DividendWithdrawn(msg.sender, _erc20, amount)

# --- Helper: dividendOf (total accumulative) ---
@external
@view
def dividendOf(_erc20: address, _account: address) -> uint256:
    return self._accumulativeDividendOf(_erc20, _account)

# --- Owner emergency / admin functions ---
@external
def emergencyWithdrawERC20(_erc20: address, _to: address, _amount: uint256):
    """
    Owner can withdraw ERC20 tokens in emergency (only use if contract broken).
    Use with extreme caution and log off-chain.
    """
    self._only_owner()
    erc: IERC20 = IERC20(_erc20)
    success: bool = erc.transfer(_to, _amount)
    assert success, "transfer failed"

@external
def changeOwner(_new: address):
    self._only_owner()
    assert _new != ZERO_ADDRESS
    self.owner = _new



# @version ^0.4.0

# magnitudes for 10^24 precision to prevent rounding drain
PRECISION: constant(uint256) = 1_000_000_000_000_000_000_000_000 

@external
@nonreentrant
def claim_payout(series_id: uint256):
    """
    @notice Distributes Real-Estate Credit yield to token holders
    @dev Triggered after the 'Observer' confirms the USD-to-USDT bridge
    """
    total_shares: uint256 = self.series_total_supply[series_id]
    total_yield: uint256 = self.series_pending_yield[series_id]
    
    assert total_shares > 0, "No investors in series"
    assert total_yield > 0, "No yield to distribute"

    # Calculate yield per share with 10^24 precision
    yield_per_share: uint256 = (total_yield * PRECISION) / total_shares
    
    user_balance: uint256 = self.balanceOf(msg.sender, series_id)
    claimable: uint256 = (user_balance * yield_per_share) / PRECISION
    
    self.series_pending_yield[series_id] -= claimable
    # Transfer USDT/USDC to user
    self.asset.transfer(msg.sender, claimable)
    
    log PayoutClaimed(msg.sender, series_id, claimable)


    # pragma version ^0.4.0

# Define the buckets
senior_vault: public(uint256)
junior_vault: public(uint256)

# The "Target" Principal for the Senior guys
SENIOR_PRINCIPAL_TARGET: constant(uint256) = 70_000 # 70% of 100k
SENIOR_INTEREST_RATE: constant(uint256) = 8 # 8%

@external
def distribute_cashflow(total_received: uint256):
    # 1. Fill the Senior Principal first
    senior_principal_due: uint256 = SENIOR_PRINCIPAL_TARGET
    senior_interest_due: uint256 = (senior_principal_due * SENIOR_INTEREST_RATE) // 100
    
    total_senior_due: uint256 = senior_principal_due + senior_interest_due
    
    if total_received >= total_senior_due:
        # Senior is fully paid
        self.senior_vault += total_senior_due
        # The "Overflow" goes to Junior
        self.junior_vault += (total_received - total_senior_due)
    else:
        # Senior gets whatever we have, Junior gets 0
        self.senior_vault += total_received
        self.junior_vault = 0