"""
Generic snapshot runner that works with any drop configuration.

Usage:
    brownie run run_snapshot yb_drop --network mainnet

Note: Brownie doesn't support custom command-line args, so all parameters
are set interactively via prompts.
"""
import click
import sys
import os
import json
from importlib import import_module
from brownie import chain

def main():
    """
    Entry point for brownie run.

    Usage:
        brownie run run_snapshot --network mainnet
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
        snapshot_path = os.path.join(entry_path, 'snapshot.py')
        config_path = os.path.join(entry_path, 'config.py')
        # Accept drops with either snapshot.py or config.py (for backwards compatibility)
        if os.path.isdir(entry_path) and (os.path.exists(snapshot_path) or os.path.exists(config_path)):
            available_drops.append(entry)

    if not available_drops:
        click.echo("Error: No drop configurations found in scripts/drops/ directory")
        click.echo("Each drop should have a directory with snapshot.py (or config.py) inside")
        sys.exit(1)

    # Display available drops
    click.echo("\nAvailable drops:")
    for i, drop in enumerate(available_drops, 1):
        click.echo(f"  {i}. {drop}")

    click.echo("\nNote: To create a new drop, create a directory in scripts/drops/ with snapshot.py")
    click.echo("Example: scripts/drops/my_drop/snapshot.py with a DropConfig class\n")

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

    # Import drop configuration (try snapshot module first for flexibility)
    try:
        snapshot_module = import_module(f'scripts.drops.{drop_dir}.snapshot')
        if hasattr(snapshot_module, 'DropConfig'):
            DropConfig = snapshot_module.DropConfig
        else:
            # Fallback: try config module
            config_module = import_module(f'scripts.drops.{drop_dir}.config')
            DropConfig = config_module.DropConfig
    except ImportError as e:
        click.echo(f"Error: Could not import DropConfig from scripts/drops/{drop_dir}/")
        click.echo(f"Make sure scripts/drops/{drop_dir}/snapshot.py has a DropConfig class")
        click.echo(f"Details: {e}")
        sys.exit(1)

    # Load configuration (from config.json if exists, otherwise from class defaults)
    config = DropConfig.load_config()
    default_block = config['block']
    default_include_lp = config['include_lp']
    default_include_untokenized = config['include_untokenized']
    default_include_firm = config['include_firm']
    default_include_ajna = config['include_ajna']
    default_include_vanilla_ycrv = config['include_vanilla_ycrv']
    default_min_amount = config['min_amount']  # Already in decimal format

    # Check if config.json exists to show appropriate message
    config_file = DropConfig.get_config_file()
    if os.path.exists(config_file):
        click.echo(f"\n✓ Loaded previous configuration from {os.path.basename(config_file)}")
        click.echo(f"  Last run: block {default_block}, min_amount: {default_min_amount} tokens\n")
    else:
        click.echo(f"\n✓ Using default configuration (no config.json found)\n")

    # Interactive prompts for all parameters
    block = click.prompt(
        'Snapshot block height ("latest" for current block)',
        default=default_block,
        show_default=True
    )

    if str(block).lower() == "latest":
        block = chain.height
        click.echo(f"Using latest block: {block}")

    block = int(block)

    include_lp = click.confirm(
        'Include LP positions?',
        default=default_include_lp
    )

    include_untokenized = click.confirm(
        'Include untokenized amounts?',
        default=default_include_untokenized
    )

    include_firm = click.confirm(
        'Include FIRM positions?',
        default=default_include_firm
    )

    include_ajna = click.confirm(
        'Include AJNA positions?',
        default=default_include_ajna
    )

    include_vanilla_ycrv = click.confirm(
        'Include vanilla yCRV balances?',
        default=default_include_vanilla_ycrv
    )

    min_amount_decimal = click.prompt(
        'Minimum amount (tokens)',
        default=default_min_amount,
        show_default=True,
        type=float
    )

    # Convert decimal to wei
    min_amount = int(min_amount_decimal * 1e18)

    # Check if output file already exists
    output_file = DropConfig.get_snapshot_file(block)
    file_exists = os.path.exists(output_file)

    # Display colorized configuration summary
    click.echo("\n" + click.style("=" * 70, fg='cyan', bold=True))
    click.echo(click.style("  SNAPSHOT CONFIGURATION", fg='cyan', bold=True))
    click.echo(click.style("=" * 70, fg='cyan', bold=True))

    click.echo(click.style("  Drop Name:            ", fg='white', bold=True) +
               click.style(f"{DropConfig.DROP_NAME}", fg='green', bold=True))

    click.echo(click.style("  Snapshot Block:       ", fg='white', bold=True) +
               click.style(f"{block:,}", fg='green', bold=True))

    click.echo(click.style("  Include LP:           ", fg='white', bold=True) +
               click.style(f"{include_lp}", fg='yellow' if include_lp else 'white'))

    click.echo(click.style("  Include Untokenized:  ", fg='white', bold=True) +
               click.style(f"{include_untokenized}", fg='yellow' if include_untokenized else 'white'))

    click.echo(click.style("  Include FIRM:         ", fg='white', bold=True) +
               click.style(f"{include_firm}", fg='yellow' if include_firm else 'white'))

    click.echo(click.style("  Include AJNA:         ", fg='white', bold=True) +
               click.style(f"{include_ajna}", fg='yellow' if include_ajna else 'white'))

    click.echo(click.style("  Include Vanilla yCRV: ", fg='white', bold=True) +
               click.style(f"{include_vanilla_ycrv}", fg='yellow' if include_vanilla_ycrv else 'white'))

    click.echo(click.style("  Min Amount:           ", fg='white', bold=True) +
               click.style(f"{min_amount / 1e18:,.2f} tokens", fg='green', bold=True))

    click.echo(click.style("  Output File:          ", fg='white', bold=True) +
               click.style(f"{output_file}", fg='magenta'))

    if file_exists:
        click.echo(click.style("  Status:               ", fg='white', bold=True) +
                   click.style("⚠️  FILE EXISTS - WILL OVERWRITE", fg='red', bold=True))
    else:
        click.echo(click.style("  Status:               ", fg='white', bold=True) +
                   click.style("✓ New file", fg='green'))

    click.echo(click.style("=" * 70, fg='cyan', bold=True) + "\n")

    # Confirmation prompt
    if file_exists:
        if not click.confirm(click.style('⚠️  File exists. Overwrite?', fg='yellow', bold=True), default=False):
            click.echo(click.style("Cancelled.", fg='red'))
            return

    if not click.confirm(click.style('Proceed with snapshot?', fg='cyan', bold=True), default=True):
        click.echo(click.style("Cancelled.", fg='red'))
        return

    # Save configuration to config.json
    config['block'] = block
    config['include_lp'] = include_lp
    config['include_untokenized'] = include_untokenized
    config['include_firm'] = include_firm
    config['include_ajna'] = include_ajna
    config['include_vanilla_ycrv'] = include_vanilla_ycrv
    config['min_amount'] = min_amount_decimal
    DropConfig.save_config(config)
    click.echo(click.style(f"✓ Configuration saved to {os.path.basename(config_file)}\n", fg='green'))

    # Import and run snapshot
    try:
        snapshot_module = import_module(f'scripts.drops.{drop_dir}.snapshot')

        # Run snapshot (reads config.json internally)
        click.echo("Starting snapshot...")
        snapshot_module.main()

        # Get output file path
        output_file = DropConfig.get_snapshot_file(block)
        click.echo(f"\n✓ Snapshot complete!")
        click.echo(f"✓ Saved to: {output_file}")

    except ImportError as e:
        click.echo(f"Error: Could not import snapshot from scripts/drops/{drop_dir}/")
        click.echo(f"Make sure scripts/drops/{drop_dir}/snapshot.py exists with a main() function")
        click.echo(f"Details: {e}")
        sys.exit(1)
    except Exception as e:
        click.echo(f"Error running snapshot: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
