# @version ^0.3.9

# MockUSDC.vy
# A testing mock for USDC on Avalanche

from ethereum.ercs import ERC20

implements: ERC20

event Transfer:
    sender: indexed(address)
    receiver: indexed(address)
    value: uint256

event Approval:
    owner: indexed(address)
    spender: indexed(address)
    value: uint256

name: public(String[32])
symbol: public(String[8])
decimals: public(uint8) # USDC uses uint8 standard

# Internal variable (underscore prefix)
_totalSupply: uint256
balances: HashMap[address, uint256]
allowances: HashMap[address, HashMap[address, uint256]]

@external
def __init__(_name: String[32], _symbol: String[8], _decimals: uint8, _initialMint: uint256):
    self.name = _name
    self.symbol = _symbol
    self.decimals = _decimals
    self._totalSupply = _initialMint
    self.balances[msg.sender] = _initialMint
    log Transfer(empty(address), msg.sender, _initialMint)

# --- ERC20 Standard Getters ---

@view
@external
def totalSupply() -> uint256:
    return self._totalSupply

@view
@external
def balanceOf(_owner: address) -> uint256:
    return self.balances[_owner]

@view
@external
def allowance(_owner: address, _spender: address) -> uint256:
    return self.allowances[_owner][_spender]

# --- ERC20 Operations ---

@external
def transfer(_to: address, _value: uint256) -> bool:
    self.balances[msg.sender] -= _value # Vyper 0.3+ has built-in overflow protection
    self.balances[_to] += _value
    log Transfer(msg.sender, _to, _value)
    return True

@external
def transferFrom(_from: address, _to: address, _value: uint256) -> bool:
    self.allowances[_from][msg.sender] -= _value
    self.balances[_from] -= _value
    self.balances[_to] += _value
    log Transfer(_from, _to, _value)
    return True

@external
def approve(_spender: address, _value: uint256) -> bool:
    self.allowances[msg.sender][_spender] = _value
    log Approval(msg.sender, _spender, _value)
    return True

# --- EXTRA: Free Mint for Testing ---
# This allows you to generate more fake USDC later in your tests
@external
def mint(_to: address, _value: uint256):
    self._totalSupply += _value
    self.balances[_to] += _value
    log Transfer(empty(address), _to, _value)