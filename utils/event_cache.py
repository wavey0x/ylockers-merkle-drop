"""
Event log caching system for expensive RPC calls.

Caches event logs (Transfer, Staked, etc.) to avoid re-scanning
the entire blockchain history on every run.
"""
import json
import os
from pathlib import Path
from typing import Set, Tuple, Optional, Dict, Any

CACHE_DIR = Path(__file__).parent.parent / "data" / "cache"
CACHE_FILE = CACHE_DIR / "event_cache.json"


def load_cache() -> Dict[str, Any]:
    """
    Load the event cache from disk.

    Returns:
        Dict with cache data, or empty structure if file doesn't exist
    """
    if not CACHE_FILE.exists():
        return {"version": "1.0", "caches": {}}

    with open(CACHE_FILE, 'r') as f:
        return json.load(f)


def save_cache(cache_data: Dict[str, Any]) -> None:
    """
    Save the event cache to disk.

    Args:
        cache_data: Complete cache dictionary to save
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(CACHE_FILE, 'w') as f:
        json.dump(cache_data, f, indent=2)


def get_cache_key(contract_address: str, event_name: str) -> str:
    """
    Generate a cache key for a contract+event combination.

    Args:
        contract_address: Contract address (will be checksummed)
        event_name: Name of the event (e.g., "Transfer", "Staked")

    Returns:
        Cache key like "0xABC123_Transfer"
    """
    # Normalize address (remove 0x prefix if present, lowercase)
    addr = contract_address.lower().replace('0x', '')
    return f"0x{addr}_{event_name}"


def get_cached_entry(contract_address: str, event_name: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific cache entry for a contract+event.

    Args:
        contract_address: Contract address
        event_name: Event name

    Returns:
        Cache entry dict or None if not found
    """
    cache = load_cache()
    key = get_cache_key(contract_address, event_name)
    return cache.get("caches", {}).get(key)


def update_cache_entry(
    contract_address: str,
    event_name: str,
    users: Set[str],
    last_scanned_block: int,
    contract_name: Optional[str] = None,
    deploy_block: Optional[int] = None
) -> None:
    """
    Update or create a cache entry.

    Args:
        contract_address: Contract address
        event_name: Event name
        users: Set of user addresses
        last_scanned_block: Last block that was scanned
        contract_name: Human-readable name (optional)
        deploy_block: Deployment block (optional, for reference)
    """
    cache = load_cache()
    key = get_cache_key(contract_address, event_name)

    cache["caches"][key] = {
        "contract_address": contract_address.lower(),
        "contract_name": contract_name or "Unknown",
        "event_name": event_name,
        "deploy_block": deploy_block,
        "last_scanned_block": last_scanned_block,
        "users": sorted(list(users))  # Sort for consistency
    }

    save_cache(cache)


def scan_events_with_cache(
    contract: Any,
    event_name: str,
    deploy_block: int,
    snapshot_height: int,
    contract_name: Optional[str] = None,
    search_topics: Optional[Dict] = None,
    chunk_size: int = 70_000
) -> Tuple[Set[str], list]:
    """
    Scan event logs with caching to avoid re-scanning old blocks.

    Args:
        contract: Contract instance (brownie)
        event_name: Name of event to scan (e.g., "Transfer")
        deploy_block: Block where contract was deployed
        snapshot_height: Target block height to scan to
        contract_name: Human-readable contract name
        search_topics: Optional filter for event logs
        chunk_size: Number of blocks to scan per request

    Returns:
        Tuple of (users_set, all_logs)
        - users_set: Set of all unique addresses involved
        - all_logs: List of all event logs (for further processing)
    """
    contract_address = contract.address

    # Load cache entry if it exists
    cached_entry = get_cached_entry(contract_address, event_name)

    if cached_entry:
        last_scanned = cached_entry["last_scanned_block"]
        cached_users = set(cached_entry["users"])

        # If snapshot is at or before last scan, use cached data
        if snapshot_height <= last_scanned:
            print(f"  [CACHE HIT] {contract_name or contract_address}/{event_name}: "
                  f"Using cached data (snapshot {snapshot_height} <= last_scanned {last_scanned})")
            # Return cached users, but we can't return cached logs (not stored)
            # So we return empty logs - caller must handle this
            return cached_users, []

        # Scan only new blocks since last scan
        start_block = last_scanned + 1
        print(f"  [CACHE] {contract_name or contract_address}/{event_name}: "
              f"Scanning blocks {start_block} to {snapshot_height} "
              f"(cached: {len(cached_users)} users from {deploy_block} to {last_scanned})")
    else:
        # No cache, scan from deployment
        start_block = deploy_block
        cached_users = set()
        print(f"  [NO CACHE] {contract_name or contract_address}/{event_name}: "
              f"Scanning blocks {start_block} to {snapshot_height}")

    # Get the event object using Brownie's API
    # Brownie events are accessed via: contract.events.EventName().getLogs()
    try:
        event = getattr(contract.events, event_name)()
    except AttributeError:
        print(f"  [ERROR] Cannot find event '{event_name}' on contract {contract_name or contract_address}")
        print(f"  Available events: {[x for x in dir(contract.events) if not x.startswith('_')]}")
        raise

    # Break large block ranges into chunks to avoid timeouts
    total_blocks = snapshot_height - start_block + 1
    num_chunks = (total_blocks + chunk_size - 1) // chunk_size  # Ceiling division

    all_logs = []
    new_users = set()

    for i in range(num_chunks):
        chunk_start = start_block + (i * chunk_size)
        chunk_end = min(chunk_start + chunk_size - 1, snapshot_height)

        # Progress indicator
        progress = (i + 1) / num_chunks * 100
        print(f"  [{progress:5.1f}%] Scanning blocks {chunk_start:,} to {chunk_end:,} "
              f"(chunk {i+1}/{num_chunks})")

        # Scan this chunk
        if search_topics:
            chunk_logs = event.get_logs(
                fromBlock=chunk_start,
                toBlock=chunk_end,
                argument_filters=search_topics
            )
        else:
            chunk_logs = event.get_logs(fromBlock=chunk_start, toBlock=chunk_end)

        all_logs.extend(chunk_logs)

        # Extract users from this chunk
        chunk_users = extract_users_from_logs(chunk_logs, event_name)
        new_users.update(chunk_users)

        print(f"           Found {len(chunk_logs)} events, {len(chunk_users)} unique addresses in this chunk")

        # Save progress after each chunk (in case of failure later)
        if i < num_chunks - 1:  # Don't save intermediate progress on last chunk
            temp_users = cached_users | new_users
            update_cache_entry(
                contract_address,
                event_name,
                temp_users,
                chunk_end,  # Save up to this block
                contract_name,
                deploy_block
            )

    # Merge with cached users
    all_users = cached_users | new_users

    # Final cache update
    update_cache_entry(
        contract_address,
        event_name,
        all_users,
        snapshot_height,
        contract_name,
        deploy_block
    )

    print(f"  [COMPLETE] {contract_name or contract_address}/{event_name}: "
          f"{len(new_users)} new users, {len(all_users)} total users")

    return all_users, all_logs


def extract_users_from_logs(logs: list, event_name: str) -> Set[str]:
    """
    Extract unique user addresses from event logs.

    Args:
        logs: List of Brownie event logs (AttributeDict with 'args' field)
        event_name: Type of event (determines which fields to extract)

    Returns:
        Set of unique addresses
    """
    users = set()

    for log in logs:
        # Brownie logs have event parameters in log['args'] or log.args
        args = log.get('args') if hasattr(log, 'get') else getattr(log, 'args', None)
        if not args:
            continue

        if event_name == "Transfer":
            # Transfer events have 'sender'/'from' and 'receiver'/'to'
            from_addr = args.get('sender') or args.get('from') or args.get('_from')
            to_addr = args.get('receiver') or args.get('to') or args.get('_to')

            if from_addr:
                users.add(from_addr)
            if to_addr:
                users.add(to_addr)

        elif event_name == "Staked":
            # Staked events typically have 'account' field
            account = args.get('account')
            if account:
                users.add(account)

        elif event_name == "CreateEscrow":
            # CreateEscrow has 'user' and 'escrow' fields
            user = args.get('user')
            escrow = args.get('escrow')
            if user:
                users.add(user)
            if escrow:
                users.add(escrow)

        elif event_name == "Deposited":
            # Deposited events have 'user' field
            user = args.get('user')
            if user:
                users.add(user)

        else:
            # Generic fallback - try common field names
            for field in ['sender', 'receiver', 'from', 'to', 'account', 'user', 'address', '_from', '_to']:
                addr = args.get(field)
                if addr:
                    users.add(addr)

    return users


def clear_cache() -> None:
    """Clear all cached data."""
    if CACHE_FILE.exists():
        CACHE_FILE.unlink()
        print(f"Cache cleared: {CACHE_FILE}")
    else:
        print("No cache file to clear")


def get_cache_stats() -> Dict[str, Any]:
    """
    Get statistics about the cache.

    Returns:
        Dict with cache statistics
    """
    cache = load_cache()
    caches = cache.get("caches", {})

    total_users = sum(len(entry["users"]) for entry in caches.values())

    return {
        "cache_file": str(CACHE_FILE),
        "cache_exists": CACHE_FILE.exists(),
        "num_cached_contracts": len(caches),
        "total_cached_users": total_users,
        "entries": {
            key: {
                "contract": entry["contract_name"],
                "event": entry["event_name"],
                "last_block": entry["last_scanned_block"],
                "num_users": len(entry["users"])
            }
            for key, entry in caches.items()
        }
    }
