import json
import click
import os
from brownie import web3
from utils.merkle import MerkleTree
from eth_utils import encode_hex
from eth_abi.packed import encode_packed
from .snapshot import DropConfig

def main(output_path=None, description=''):
    """
    Entry point for brownie run.

    Generate merkle root for YB token distribution based on yCRV snapshot.
    Auto-detects the latest snapshot file or prompts for path.

    Args:
        output_path: Optional custom output path for the merkle data.
                     If not provided, uses the default from config.json
        description: Optional description/name for this drop
    """
    # Load configuration
    config = DropConfig.load_config()
    snapshot_dir = config.get('snapshot_dir', DropConfig.SNAPSHOT_DIR)
    merkle_output = output_path if output_path else config.get('merkle_output', DropConfig.MERKLE_OUTPUT)
    total_tokens = int(config.get('total_tokens', DropConfig.TOTAL_TOKENS))

    # Auto-detect latest snapshot file
    snapshot = DropConfig.get_latest_snapshot()

    if snapshot is None:
        click.echo(f"Error: No snapshot files found in {snapshot_dir}")
        click.echo(f"Run 'brownie run run_snapshot' first to generate a snapshot")
        return

    click.echo(f"Using snapshot: {snapshot}")

    # Check if merkle output already exists
    if os.path.exists(merkle_output):
        click.echo(f"\n⚠️  WARNING: {merkle_output} already exists!")
        if not click.confirm('Overwrite existing merkle distribution?', default=False):
            click.echo("Cancelled.")
            return

    # Load the yCRV snapshot data
    with open(snapshot, 'r') as f:
        snapshot_data = json.load(f)

    # Extract the values dict: {address: yCRV_amount_in_ether}
    ycrv_amounts = snapshot_data['values']
    snapshot_total = snapshot_data['total']

    # Display snapshot metadata if available
    if 'metadata' in snapshot_data:
        meta = snapshot_data['metadata']
        click.echo(f"\nSnapshot Metadata:")
        click.echo(f"  Drop: {meta.get('drop_name', 'unknown')}")
        click.echo(f"  Block: {meta.get('snapshot_height', 'unknown')}")
        click.echo(f"  Include LP: {meta.get('include_lp', 'unknown')}")
        click.echo(f"  Generated: {meta.get('generated_at', 'unknown')}")

    click.echo(f"\nLoaded {len(ycrv_amounts)} addresses from yCRV snapshot")
    click.echo(f"Total yCRV in snapshot: {snapshot_total:,.2f}")
    click.echo(f"Total YB to distribute: {total_tokens / 1e18:,.2f}")

    # Calculate proportional YB distribution
    # Convert yCRV amounts (in ether) to wei for precision
    ycrv_amounts_wei = {addr: int(amount * 1e18) for addr, amount in ycrv_amounts.items()}
    total_ycrv_wei = sum(ycrv_amounts_wei.values())

    # Calculate YB allocation per address (proportional to yCRV holdings)
    yb_amounts = {
        addr.lower(): (ycrv_wei * total_tokens) // total_ycrv_wei
        for addr, ycrv_wei in ycrv_amounts_wei.items()
    }

    # Handle rounding dust: add remainder to largest holder
    addresses_sorted = sorted(yb_amounts, key=lambda k: yb_amounts[k], reverse=True)
    current_total = sum(yb_amounts.values())
    if current_total < total_tokens:
        diff = total_tokens - current_total
        yb_amounts[addresses_sorted[0]] += diff
        click.echo(f"Added {diff / 1e18:.18f} YB rounding dust to largest holder")

    # Verify total matches exactly
    final_total = sum(yb_amounts.values())
    assert final_total == total_tokens, f"Total mismatch: {final_total} != {total_tokens}"

    click.echo(f"\nDistribution calculated for {len(yb_amounts)} users")
    click.echo(f"Verified total: {final_total / 1e18:,.2f} YB")

    # Create merkle tree
    elements = [
        (account, index, yb_amounts[account])
        for index, account in enumerate(addresses_sorted)
    ]
    nodes = [encode_hex(encode_packed(["address", "uint", "uint"], el)) for el in elements]
    tree = MerkleTree(nodes)

    distribution = {
        "description": description,
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
    os.makedirs(os.path.dirname(merkle_output), exist_ok=True)
    with open(merkle_output, 'w') as f:
        json.dump(distribution, f, indent=4)

    click.echo(f"\n✓ Merkle distribution written to {merkle_output}")
    click.echo(f"✓ Merkle root: {encode_hex(tree.root)}")
    click.echo(f"✓ {len(distribution['claims'])} claims generated")

    # Print top 10 recipients for verification
    click.echo("\nTop 10 YB recipients:")
    for i, addr in enumerate(addresses_sorted[:10]):
        click.echo(f"  {i+1}. {web3.to_checksum_address(addr)}: {yb_amounts[addr] / 1e18:,.2f} YB")

    # Calculate and display distribution statistics
    amounts_list = [yb_amounts[addr] / 1e18 for addr in addresses_sorted]
    total_users = len(amounts_list)
    min_amount = amounts_list[-1] if amounts_list else 0  # Last in sorted list (lowest)
    max_amount = amounts_list[0] if amounts_list else 0  # First in sorted list (highest)
    avg_amount = sum(amounts_list) / total_users if total_users > 0 else 0

    # Calculate median
    if total_users == 0:
        median_amount = 0
    elif total_users % 2 == 1:
        median_amount = amounts_list[total_users // 2]
    else:
        median_amount = (amounts_list[total_users // 2 - 1] + amounts_list[total_users // 2]) / 2

    click.echo("\n" + click.style("━" * 70, fg='cyan'))
    click.echo(click.style("  DISTRIBUTION STATISTICS", fg='cyan', bold=True))
    click.echo(click.style("━" * 70, fg='cyan'))
    click.echo(f"  Total Recipients:  {total_users:,}")
    click.echo(f"  Maximum Amount:    {max_amount:,.2f} YB")
    click.echo(f"  Average Amount:    {avg_amount:,.2f} YB")
    click.echo(f"  Median Amount:     {median_amount:,.2f} YB")
    click.echo(f"  Minimum Amount:    {min_amount:,.2f} YB")
    click.echo(click.style("━" * 70, fg='cyan'))
