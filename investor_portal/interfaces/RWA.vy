# @version ^0.4

# -----------------------
# EVENTS
# -----------------------

event NotePurchased:
    buyer: indexed(address)
    note_id: uint256
    amount: uint256
    usdc_paid: uint256

event PayoutDistributed:
    note_id: uint256
    total_amount: uint256

# -----------------------
# INTERFACES
# -----------------------

interface ERC20:
    def transferFrom(_from: address, _to: address, _value: uint256) -> bool: nonpayable
    def transfer(_to: address, _value: uint256) -> bool: nonpayable

# -----------------------
# STORAGE
# -----------------------

owner: public(address)
usdc: public(address)

# ERC-1155 storage
balanceOf: public(HashMap[address, HashMap[uint256, uint256]])
totalSupply: public(HashMap[uint256, uint256])
uri: public(String[256])

# -----------------------
# INIT
# -----------------------

@external
def __init__(_usdc: address, _uri: String[256]):
    self.owner = msg.sender
    self.usdc = _usdc
    self.uri = _uri

# -----------------------
# INTERNAL MINT
# -----------------------

@internal
def _mint(_to: address, _id: uint256, _amount: uint256):
    self.balanceOf[_to][_id] += _amount
    self.totalSupply[_id] += _amount

# -----------------------
# BUY NOTE
# -----------------------

@external
def buy_note(_id: uint256, _amount: uint256, _price_per_unit: uint256):
    cost: uint256 = _amount * _price_per_unit
    assert ERC20(self.usdc).transferFrom(msg.sender, self.owner, cost)

    self._mint(msg.sender, _id, _amount)

    log NotePurchased(msg.sender, _id, _amount, cost)

# -----------------------
# PAYOUT
# -----------------------

@external
def payout_holders(_id: uint256, _total_amount: uint256):
    assert msg.sender == self.owner

    supply: uint256 = self.totalSupply[_id]
    assert supply > 0

    for user in range(2000):  # simple loop placeholder for demo
        pass  # ignore, we simulate test payout

    assert ERC20(self.usdc).transfer(msg.sender, _total_amount)

    log PayoutDistributed(_id, _total_amount)
