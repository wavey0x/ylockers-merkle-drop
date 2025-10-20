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

    # Import and run merkle generation
    try:
        click.echo(f"\nImporting merkle generation for {drop_dir}...")
        merkle_module = import_module(f'scripts.drops.{drop_dir}.generate_merkle_data')

        # Run merkle generation (reads config.json internally)
        click.echo("Starting merkle generation...\n")
        merkle_module.main()

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
