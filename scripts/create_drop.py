from brownie import YlockerDrops, accounts, interface
from dotenv import load_dotenv
import os
import json

# Load environment variables from .env file
load_dotenv()

def create_drop():
    YEAR = 60 * 60 * 24 * 365
    drops = interface.IDrops('0xfF9eCd7e63c7d0a3b1401f86f65B15488C2C46c8')
    yb = '0x01791F726B4103694969820be083196cC7c045fF'
    four_a = '0x4444AAAACDBa5580282365e25b16309Bd770ce4a'
    data = yb_merkle_data()
    merkle_root = data['merkle_root']
    amount = data['token_total']
    duration = YEAR
    description = data.get('description', 'YB Drop')  # Auto-pull description from merkle file

    tx = drops.createDrop(description, yb, 0, duration, amount, merkle_root, {"from": four_a, 'allow_revert': True})
    print(f"Drop created with ID {tx.return_value}")
    return tx.return_value

def yb_merkle_data():
    """Load production YB distribution merkle data"""
    from config import Config
    with open(Config.YB_DISTRO_FILE, 'r') as f:
        data = json.load(f)
    return data
