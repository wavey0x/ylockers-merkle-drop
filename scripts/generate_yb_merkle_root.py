import json
from brownie import web3
from utils.merkle import MerkleTree
from eth_utils import encode_hex
from eth_abi.packed import encode_packed
from config import Config

# Total YB tokens to distribute: 116,459.57 YB = 116459.57e18 wei
TOTAL_YB_DISTRIBUTION = 116_459_570000000000000000

def main():
    """
    Generate merkle root for YB token distribution based on yCRV snapshot.

    Reads proportional yCRV holdings from ycrv_snapshot.json and distributes
    TOTAL_YB_DISTRIBUTION proportionally across all holders.
    """
    # Load the yCRV snapshot data
    with open(Config.YCRV_SNAPSHOT_FILE, 'r') as f:
        snapshot_data = json.load(f)

    # Extract the values dict: {address: yCRV_amount_in_ether}
    ycrv_amounts = snapshot_data['values']
    snapshot_total = snapshot_data['total']

    print(f"Loaded {len(ycrv_amounts)} addresses from yCRV snapshot")
    print(f"Total yCRV in snapshot: {snapshot_total:,.2f}")
    print(f"Total YB to distribute: {TOTAL_YB_DISTRIBUTION / 1e18:,.2f}")

    # Calculate proportional YB distribution
    # Convert yCRV amounts (in ether) to wei for precision
    ycrv_amounts_wei = {addr: int(amount * 1e18) for addr, amount in ycrv_amounts.items()}
    total_ycrv_wei = sum(ycrv_amounts_wei.values())

    # Calculate YB allocation per address (proportional to yCRV holdings)
    yb_amounts = {
        addr.lower(): (ycrv_wei * TOTAL_YB_DISTRIBUTION) // total_ycrv_wei
        for addr, ycrv_wei in ycrv_amounts_wei.items()
    }

    # Handle rounding dust: add remainder to largest holder
    addresses_sorted = sorted(yb_amounts, key=lambda k: yb_amounts[k], reverse=True)
    current_total = sum(yb_amounts.values())
    if current_total < TOTAL_YB_DISTRIBUTION:
        diff = TOTAL_YB_DISTRIBUTION - current_total
        yb_amounts[addresses_sorted[0]] += diff
        print(f"Added {diff / 1e18:.18f} YB rounding dust to largest holder")

    # Verify total matches exactly
    final_total = sum(yb_amounts.values())
    assert final_total == TOTAL_YB_DISTRIBUTION, f"Total mismatch: {final_total} != {TOTAL_YB_DISTRIBUTION}"

    print(f"\nDistribution calculated for {len(yb_amounts)} users")
    print(f"Verified total: {final_total / 1e18:,.2f} YB")

    # Create merkle tree
    elements = [
        (account, index, yb_amounts[account])
        for index, account in enumerate(addresses_sorted)
    ]
    nodes = [encode_hex(encode_packed(["address", "uint", "uint"], el)) for el in elements]
    tree = MerkleTree(nodes)

    distribution = {
        "merkle_root": encode_hex(tree.root),
        "token_total": str(final_total),
        "num_recipients": len(yb_amounts),
        "claims": {
            web3.to_checksum_address(user): {
                "index": index,
                "amount": str(amount),
                "proof": tree.get_proof(nodes[index]),
            }
            for user, index, amount in elements
        },
    }

    # Write merkle distribution to output file
    with open(Config.YB_DISTRO_FILE, 'w') as f:
        json.dump(distribution, f, indent=4)

    print(f"\n✓ Merkle distribution written to {Config.YB_DISTRO_FILE}")
    print(f"✓ Merkle root: {encode_hex(tree.root)}")
    print(f"✓ {len(distribution['claims'])} claims generated")

    # Print top 10 recipients for verification
    print("\nTop 10 YB recipients:")
    for i, addr in enumerate(addresses_sorted[:10]):
        print(f"  {i+1}. {web3.to_checksum_address(addr)}: {yb_amounts[addr] / 1e18:,.2f} YB")
