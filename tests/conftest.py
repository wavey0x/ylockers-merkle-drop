import pytest, requests
from brownie import ZERO_ADDRESS, config, Contract, web3, chain, YlockerDrops


# This causes test not to re-run fixtures on each run
@pytest.fixture(autouse=True)
def isolation(fn_isolation):
    pass


@pytest.fixture
def gov(accounts):
    # Use anvil's default account which has a private key
    yield accounts[0]


@pytest.fixture
def dai():
    yield Contract("0x6B175474E89094C44Da98b954EedeAC495271d0F")

@pytest.fixture
def dai_whale(accounts, web3, dai):
    # Use accounts[1] and give it DAI via storage manipulation
    whale = accounts[1]
    from eth_abi import encode
    from eth_utils import keccak
    key = int(whale.address, 16)
    slot_index = 2
    packed = encode(['address', 'uint256'], [whale.address, slot_index])
    slot_hash = '0x' + keccak(packed).hex()
    balance_value = 10_000_000 * 10**18
    balance = '0x' + hex(balance_value)[2:].zfill(64)
    web3.provider.make_request("anvil_setStorageAt", [dai.address, slot_hash, balance])
    yield whale

@pytest.fixture
def drops(gov):
    drops = YlockerDrops.deploy(gov, {"from": gov})
    yield drops

@pytest.fixture
def create_drop(drops, dai, dai_whale, gov):
    """
    Fixture that returns a factory function to create drops with sensible defaults.

    Usage: drop_id, tx = create_drop()  # All defaults
           drop_id, tx = create_drop(amount=50_000 * 10**18)  # Custom
    """
    def _create_drop(amount=None,
                     token=None,
                     duration=None,
                     merkle_root=None,
                     funder=None):
        # Set defaults
        if amount is None:
            amount = 100_000 * 10**18
        if token is None:
            token = dai.address
        if duration is None:
            duration = 86400 * 7  # 7 days
        if merkle_root is None:
            merkle_root = "0x" + "00" * 32
        if funder is None:
            funder = dai_whale

        # Fund the contract
        token_contract = Contract(token) if isinstance(token, str) else token
        token_contract.transfer(drops.address, amount, {"from": funder})

        # Create the drop
        drop_id = drops.dropCount()
        tx = drops.createDrop(token, 0, duration, amount, merkle_root, {"from": gov})

        return drop_id, tx

    return _create_drop

@pytest.fixture
def yb_merkle_data():
    """Load production YB distribution merkle data"""
    import json
    from config import Config
    with open(Config.YB_DISTRO_FILE, 'r') as f:
        data = json.load(f)
    yield data

@pytest.fixture
def yb_token():
    """Use DAI as stand-in for YB token in tests"""
    yield Contract("0x6B175474E89094C44Da98b954EedeAC495271d0F")