from ape import accounts

def get_admin():
    """
    SPV / Admin signer
    """
    return accounts.load("deployer")
