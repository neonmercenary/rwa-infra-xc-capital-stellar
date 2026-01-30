import pytest
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
RWA_CONTRACT = CONTRACTS / "RWA1155.vy"
MOCK_ERC20 = CONTRACTS / "MockERC20.vy"


@pytest.fixture(scope="session")
def check_deps():
    # Skip the test suite if required tools are not installed (vyper, web3, eth_tester)
    missing = []
    try:
        import web3  # type: ignore
        import eth_tester  # type: ignore
        import vyper  # type: ignore
    except Exception:
        pytest.skip("web3/eth_tester/vyper not installed; full integration tests skipped")


def compile_contract(path: Path) -> dict:
    # compile abi and bytecode using vyper python API if available, otherwise via CLI
    try:
        import vyper as vy
        compiled = vy.compile_codes({str(path): path.read_text()}, ['abi', 'bytecode'])
        data = compiled[str(path)]
        return data
    except Exception:
        # fallback to vyper CLI
        abi = subprocess.check_output(["vyper", "-f", "abi", str(path)]).decode()
        bytecode = subprocess.check_output(["vyper", "-f", "bytecode", str(path)]).decode()
        return {"abi": abi, "bytecode": bytecode}


def test_compile_and_deploy_local(check_deps):
    # This test compiles contracts and does a minimal deploy on eth-tester; heavy but useful when deps are present.
    import vyper as vy
    from web3 import Web3
    from eth_tester import EthereumTester, PyEVMBackend

    compiled_mock = compile_contract(MOCK_ERC20)
    compiled_rwa = compile_contract(RWA_CONTRACT)

    w3 = Web3(Web3.EthereumTesterProvider(EthereumTester(PyEVMBackend())))
    acct = w3.eth.accounts[0]

    # deploy mock ERC20
    abi_mock = compiled_mock['abi'] if isinstance(compiled_mock['abi'], list) else vy.compile_codes({str(MOCK_ERC20): MOCK_ERC20.read_text()}, ['abi'])[str(MOCK_ERC20)]['abi']
    byte_mock = compiled_mock['bytecode'] if isinstance(compiled_mock['bytecode'], str) else compiled_mock['bytecode']

    Mock = w3.eth.contract(abi=abi_mock, bytecode=byte_mock)
    tx_hash = Mock.constructor("MockUSD", "MUSDC", 6, 10**12).transact({'from': acct})
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    mock_addr = tx_receipt.contractAddress

    # deploy RWA contract
    abi_rwa = compiled_rwa['abi'] if isinstance(compiled_rwa['abi'], list) else vy.compile_codes({str(RWA_CONTRACT): RWA_CONTRACT.read_text()}, ['abi'])[str(RWA_CONTRACT)]['abi']
    byte_rwa = compiled_rwa['bytecode'] if isinstance(compiled_rwa['bytecode'], str) else compiled_rwa['bytecode']

    RWA = w3.eth.contract(abi=abi_rwa, bytecode=byte_rwa)
    tx_hash = RWA.constructor("RWA Notes", "RWA", mock_addr).transact({'from': acct})
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    rwa_addr = tx_receipt.contractAddress

    # basic sanity: contract addresses exist
    assert w3.eth.get_code(mock_addr) != b''
    assert w3.eth.get_code(rwa_addr) != b''
