"""
Generic merkle data generator that works with any drop configuration.

Usage:
    brownie run generate_merkle_data --network mainnet

Note: This script auto-detects available drops and runs their merkle generation.
Each drop's generate_merkle_data.py reads from its own config.json.
"""
import click
import sys
import os
from importlib import import_module
from brownie import Contract


def main():
    """
    Entry point for brownie run.

    Usage:
        brownie run generate_merkle_data --network mainnet
    """
    # Auto-detect available drops by scanning scripts/drops/ directory
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    drops_dir = os.path.join(scripts_dir, 'drops')
    available_drops = []

    if not os.path.exists(drops_dir):
        click.echo("Error: scripts/drops/ directory not found")
        sys.exit(1)

    for entry in os.listdir(drops_dir):
        entry_path = os.path.join(drops_dir, entry)
        merkle_script = os.path.join(entry_path, 'generate_merkle_data.py')
        if os.path.isdir(entry_path) and os.path.exists(merkle_script):
            available_drops.append(entry)

    if not available_drops:
        click.echo("Error: No merkle generation scripts found in scripts/drops/ directory")
        click.echo("Each drop should have a directory with generate_merkle_data.py inside")
        sys.exit(1)

    # Display available drops
    click.echo("\nAvailable drops for merkle generation:")
    for i, drop in enumerate(available_drops, 1):
        click.echo(f"  {i}. {drop}")

    click.echo("\nNote: To add merkle generation for a new drop, create generate_merkle_data.py")
    click.echo("Example: scripts/drops/my_drop/generate_merkle_data.py with a main() function\n")

    # Prompt user to select drop
    if len(available_drops) == 1:
        drop_dir = available_drops[0]
        click.echo(f"\nUsing only available drop: {drop_dir}")
    else:
        choice = click.prompt(
            '\nSelect drop number',
            type=click.IntRange(1, len(available_drops))
        )
        drop_dir = available_drops[choice - 1]
        click.echo(f"Selected: {drop_dir}")

    # Load drop configuration to display and confirm
    try:
        drop_module = import_module(f'scripts.drops.{drop_dir}.snapshot')
        DropConfig = drop_module.DropConfig
        config = DropConfig.load_config()

        # Display configuration details
        click.echo("\n" + click.style("=" * 70, fg='cyan'))
        click.echo(click.style("  DROP CONFIGURATION", fg='cyan', bold=True))
        click.echo(click.style("=" * 70, fg='cyan'))
        total_tokens_value = int(config.get('total_tokens', DropConfig.TOTAL_TOKENS))
        click.echo(f"  Drop Name:      {config.get('drop_name', DropConfig.DROP_NAME)}")
        click.echo(f"  Total Tokens:   {total_tokens_value / 1e18:,.2f} ({total_tokens_value} wei)")
        click.echo(f"  Snapshot Block: {config.get('block', DropConfig.DEFAULT_BLOCK)}")
        click.echo(f"  Snapshot Dir:   {config.get('snapshot_dir', DropConfig.SNAPSHOT_DIR)}")
        click.echo(f"  Merkle Output:  {config.get('merkle_output', DropConfig.MERKLE_OUTPUT)}")
        click.echo(click.style("=" * 70, fg='cyan'))

        if not click.confirm('\nConfirm the above configuration?', default=True):
            click.echo("Cancelled.")
            sys.exit(0)

    except Exception as e:
        click.echo(f"Warning: Could not load drop configuration: {e}")
        click.echo("Continuing anyway...")

    # Ask for drop description/name
    click.echo("\n" + click.style("=" * 70, fg='green'))
    click.echo(click.style("  DROP DESCRIPTION", fg='green', bold=True))
    click.echo(click.style("=" * 70, fg='green'))
    click.echo("\nEnter a name/description for this drop (e.g., 'YB Drop #1', 'Initial YB Distribution')")
    description = click.prompt('Description', type=str, default='')

    if description:
        click.echo(f"\n✓ Description set to: '{description}'")
    else:
        click.echo("\n⚠ No description provided")

    # Ask if this is a dry-run or final
    click.echo("\n" + click.style("=" * 70, fg='yellow'))
    click.echo(click.style("  RUN MODE SELECTION", fg='yellow', bold=True))
    click.echo(click.style("=" * 70, fg='yellow'))
    click.echo("\n  1. Dry Run - Testing/development (output: data/merkle/{drop_name}.json)")
    click.echo("  2. Final - Production deployment (output: data/merkle/drop-{id}.json)")
    click.echo("\n" + click.style("=" * 70, fg='yellow'))

    run_mode = click.prompt(
        '\nSelect run mode',
        type=click.IntRange(1, 2)
    )
    is_final = run_mode == 2

    output_path = None
    if is_final:
        # Query contract for drop count
        drops_contract_address = '0xfF9eCd7e63c7d0a3b1401f86f65B15488C2C46c8'
        try:
            click.echo(f"\nQuerying dropCount from contract {drops_contract_address}...")
            drops_contract = Contract(drops_contract_address)
            drop_count = drops_contract.dropCount()
            drop_id = f"{drop_count:02d}"

            click.echo(f"✓ Current dropCount: {drop_count}")
            click.echo(f"✓ This will be drop ID: {drop_count}")
            click.echo(f"✓ Output filename: drop-{drop_id}.json")

            # Confirm with user
            if not click.confirm(f'\nProceed with final generation for drop-{drop_id}.json?', default=True):
                click.echo("Cancelled.")
                sys.exit(0)

            # Set output path for final run
            output_path = os.path.join(scripts_dir, '..', 'data', 'merkle', f'drop-{drop_id}.json')
            output_path = os.path.abspath(output_path)

        except Exception as e:
            click.echo(f"Error querying contract: {e}")
            click.echo("Make sure you're connected to the correct network")
            sys.exit(1)
    else:
        click.echo(f"\nRunning in DRY RUN mode - output will use default naming")

    # Import and run merkle generation
    try:
        click.echo(f"\nImporting merkle generation for {drop_dir}...")
        merkle_module = import_module(f'scripts.drops.{drop_dir}.generate_merkle_data')

        # Run merkle generation (reads config.json internally)
        click.echo("Starting merkle generation...\n")
        if output_path:
            merkle_module.main(output_path=output_path, description=description)
        else:
            merkle_module.main(description=description)

    except ImportError as e:
        click.echo(f"Error: Could not import generate_merkle_data from scripts/drops/{drop_dir}/")
        click.echo(f"Make sure scripts/drops/{drop_dir}/generate_merkle_data.py exists with a main() function")
        click.echo(f"Details: {e}")
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error running merkle generation: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
