from brownie import YlockerDrops, accounts, interface, Contract
from dotenv import load_dotenv
import os
from brownie_safe import BrownieSafe

# Load environment variables from .env file
load_dotenv()

def main():
    deployer_id = os.getenv('DEPLOYER_ID')
    print(f"Deploying with account {deployer_id}")
    deployer = accounts.load(deployer_id)
    drops = YlockerDrops.deploy(deployer, {"from": deployer}, publish_source=True)
    print(f"Drop deployed to {drops.address}")

def create_drop():
    safe = BrownieSafe('0x4444AAAACDBa5580282365e25b16309Bd770ce4a')
    drops = safe.contract('0xfF9eCd7e63c7d0a3b1401f86f65B15488C2C46c8')
    yb = safe.contract('0x01791F726B4103694969820be083196cC7c045fF')
    data = yb_merkle_data()
    merkle_root = data['merkle_root']
    amount = data['token_total']
    duration = 60 * 60 * 24 * 365
    description = data.get('description', 'YB Drop')  # Auto-pull description from merkle file

    # yb.transfer(drops.address, amount)
    tx = drops.createDrop(description, yb, 0, duration, amount, merkle_root)
    tx = drops.setMerkleRoot(0, '0x' + '00' * 32)
    drops.setDropDescription(0, 'cancelled')

    safe_tx = safe.multisend_from_receipts()
    safe.post_transaction(safe_tx)

def claim_4a_drop():
    yb = Contract('0x01791F726B4103694969820be083196cC7c045fF')
    safe = BrownieSafe('0x4444AAAACDBa5580282365e25b16309Bd770ce4a')
    drops = safe.contract('0xfF9eCd7e63c7d0a3b1401f86f65B15488C2C46c8')
    drop_id = drops.dropCount() - 1
    data = yb_merkle_data()
    claim = data['claims'][safe.address]
    index = claim['index']
    amount = int(claim['amount'])
    proof = claim['proof']
    print(f"Claiming for {safe.address} with amount {amount/1e18:.2f} tokens and index {index} ....")
    tx = drops.claim(drop_id, safe.address, safe.address, amount, proof, index, {"from": safe.address, 'allow_revert': True})
    assert yb.balanceOf(safe.address) >= amount
    safe_tx = safe.multisend_from_receipts()
    safe.post_transaction(safe_tx)

def claim_drop():
    drop_id = 0
    drops = Contract('0xfF9eCd7e63c7d0a3b1401f86f65B15488C2C46c8')
    data = yb_merkle_data()
    claims = data['claims']
    accounts_to_test = list(claims.items())[:3]
    yb = Contract('0x01791F726B4103694969820be083196cC7c045fF')
    for account, claim_info in accounts_to_test:
        index = claim_info['index']
        amount = int(claim_info['amount'])
        proof = claim_info['proof']

        print(f"\nClaiming for {account}:")
        print(f"  Index: {index}")
        print(f"  Amount: {amount / 1e18:.2f} tokens ({amount} wei)")

        before_balance = yb.balanceOf(account)
        tx = drops.claim(
            drop_id,
            account,
            account,
            amount,
            proof,
            index,
            {"from": account, 'allow_revert': True}
        )
        assert yb.balanceOf(account) > before_balance

def yb_merkle_data():
    """Load production YB distribution merkle data"""
    import json
    from config import Config
    with open(Config.YB_DISTRO_FILE, 'r') as f:
        data = json.load(f)
    return data