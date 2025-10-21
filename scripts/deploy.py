from brownie import YlockerDrops, accounts
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

def main():
    deployer_id = os.getenv('DEPLOYER_ID')
    print(f"Deploying with account {deployer_id}")
    deployer = accounts.load(deployer_id)
    drops = YlockerDrops.deploy(deployer, {"from": deployer}, publish_source=True)
    print(f"Drop deployed to {drops.address}")