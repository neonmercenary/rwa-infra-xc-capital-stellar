import pytest
from pathlib import Path


def test_contract_file_exists():
    """Verify that the RWA1155 contract file exists."""
    contract_path = Path(__file__).resolve().parents[1] / "contracts" / "RWA1155.vy"
    assert contract_path.exists(), f"Contract not found at {contract_path}"


def test_vyper_compile(project):
    """
    Test that the RWA1155 contract compiles successfully using Ape.
    
    The project fixture in Ape automatically compiles contracts in the contracts/ directory.
    Accessing the contract will trigger compilation if it hasn't been done yet.
    """
    # Access the compiled contract - this will raise if compilation failed
    contract = project.RWA1155
    assert contract is not None, "RWA1155 contract should be compiled and available"
