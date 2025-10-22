from brownie import Contract, accounts, chain, web3, multicall, ZERO_ADDRESS
from json import dump
from collections import defaultdict
from datetime import datetime
from utils.constants import YCRV
from utils.event_cache import scan_events_with_cache
import os
import re
import json


class DropConfig:
    """Configuration for this token distribution snapshot"""

    # Drop identification
    DROP_NAME = "yb"

    # Snapshot parameters (CLI defaults)
    DEFAULT_BLOCK = 23582414
    DEFAULT_INCLUDE_LP = False
    DEFAULT_INCLUDE_UNTOKENIZED = False
    DEFAULT_INCLUDE_FIRM = False
    DEFAULT_INCLUDE_AJNA = False
    DEFAULT_INCLUDE_VANILLA_YCRV = False
    DEFAULT_MIN_AMOUNT = 500.0  # in tokens (not wei)

    # Output paths
    SNAPSHOT_DIR = f'data/snapshot/{DROP_NAME}'
    MERKLE_OUTPUT = f'data/merkle/{DROP_NAME}.json'

    # Distribution parameters (for merkle generation)
    TOTAL_TOKENS = 116_459_570000000000000000  # 116,459.57 YB

    @classmethod
    def get_config_file(cls):
        """Get path to config.json for this drop"""
        return os.path.join(os.path.dirname(__file__), 'config.json')

    @classmethod
    def load_config(cls):
        """
        Load configuration from config.json if it exists.
        Returns dict with all config values, falling back to class defaults.
        """
        config_file = cls.get_config_file()
        config = {
            'drop_name': cls.DROP_NAME,
            'snapshot_dir': cls.SNAPSHOT_DIR,
            'merkle_output': cls.MERKLE_OUTPUT,
            'total_tokens': str(cls.TOTAL_TOKENS),
            'block': cls.DEFAULT_BLOCK,
            'include_lp': cls.DEFAULT_INCLUDE_LP,
            'include_untokenized': cls.DEFAULT_INCLUDE_UNTOKENIZED,
            'include_firm': cls.DEFAULT_INCLUDE_FIRM,
            'include_ajna': cls.DEFAULT_INCLUDE_AJNA,
            'include_vanilla_ycrv': cls.DEFAULT_INCLUDE_VANILLA_YCRV,
            'min_amount': cls.DEFAULT_MIN_AMOUNT,
        }

        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    saved_config = json.load(f)
                    config.update(saved_config)
            except Exception as e:
                print(f"Warning: Could not load config.json: {e}")

        return config

    @classmethod
    def save_config(cls, config):
        """
        Save configuration to config.json

        Args:
            config: Dict with configuration values
        """
        config_file = cls.get_config_file()
        config['last_updated'] = datetime.now().isoformat()

        os.makedirs(os.path.dirname(config_file), exist_ok=True)
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)

    @classmethod
    def get_snapshot_file(cls, block_height):
        """Get the snapshot file path for a given block height"""
        config = cls.load_config()
        snapshot_dir = config.get('snapshot_dir', cls.SNAPSHOT_DIR)
        return f'{snapshot_dir}/snapshot_{block_height}.json'

    @classmethod
    def get_latest_snapshot(cls):
        """Find the most recent snapshot file"""
        config = cls.load_config()
        snapshot_dir = config.get('snapshot_dir', cls.SNAPSHOT_DIR)

        if not os.path.exists(snapshot_dir):
            return None

        pattern = re.compile(r'snapshot_(\d+)\.json')
        snapshots = []

        for filename in os.listdir(snapshot_dir):
            match = pattern.match(filename)
            if match:
                block = int(match.group(1))
                snapshots.append((block, os.path.join(snapshot_dir, filename)))

        if not snapshots:
            return None

        # Return path of highest block number
        return sorted(snapshots, key=lambda x: x[0], reverse=True)[0][1]


# Mapping of event types to all possible field name variants across different contracts
ADDRESS_KEYS_BY_EVENT = {
    "Transfer": ["receiver", "sender", "_to", "_from", "to", "from"],
    "Staked":   ["account"],
    "Deposited": ["user"],
    "CreateEscrow": ["user", "escrow"],
}

# Configuration constants
MULTICALL_CHUNK_SIZE = 500  # Number of users to process per multicall batch
EOF_BYTECODE_PREFIX = '0xef0100'  # EIP-3540 EOF (EVM Object Format) bytecode marker
EOF_BYTECODE_PREFIX_NO_PREFIX = 'ef0100'  # EOF marker without 0x prefix

def extract_addresses(logs, event):
    """
    Extract all addresses from event logs, handling field name variants.

    Different contracts use different field names for the same conceptual fields:
    - Yearn vaults: sender/receiver
    - Curve gauge: _from/_to
    - Standard ERC20: from/to
    - YBS staking: account
    - Convex deposits: user

    Args:
        logs: List of event logs
        event: Event name (e.g., "Transfer", "Staked")

    Returns:
        Set of unique addresses found in the logs
    """
    keys = ADDRESS_KEYS_BY_EVENT.get(event, [])
    out = set()
    for lg in logs or []:
        args = lg.get('args') if hasattr(lg, 'get') else getattr(lg, 'args', None)
        if not args:
            continue
        for k in keys:
            v = args.get(k)
            if v and v != ZERO_ADDRESS:
                out.add(v)
    return out

def main():
    # ycrv()
    ycrv_positions()

def ycrv_positions():
    # Load runtime configuration
    config = DropConfig.load_config()
    SNAPSHOT_HEIGHT = config['block']
    MIN_AMOUNT = int(config['min_amount'] * 1e18)  # Convert decimal to wei
    include_lp = config['include_lp']
    include_untokenized = config['include_untokenized']
    include_firm = config['include_firm']
    include_ajna = config['include_ajna']
    include_vanilla_ycrv = config['include_vanilla_ycrv']

    print(f"\n{'='*60}")
    print(f"Running snapshot with configuration:")
    print(f"  Block: {SNAPSHOT_HEIGHT}")
    print(f"  Min Amount: {config['min_amount']} tokens ({MIN_AMOUNT} wei)")
    print(f"  Include LP: {include_lp}")
    print(f"  Include Untokenized: {include_untokenized}")
    print(f"  Include FIRM: {include_firm}")
    print(f"  Include AJNA: {include_ajna}")
    print(f"  Include Vanilla yCRV: {include_vanilla_ycrv}")
    print(f"{'='*60}\n")

    ve = Contract(YCRV['VECRV'])
    ycrv = Contract(YCRV['YCRV'])
    st_ycrv = Contract(YCRV['ST_YCRV'])
    ybs = Contract(YCRV['YBS'])
    lp_ycrv_v2 = Contract(YCRV['LP_YCRV_V2'])
    helper = Contract(YCRV['AJNA_HELPER'])
    users = set()

    # Fetch all unique st-yCRV users (cached)
    cached_st_users, st_logs = scan_events_with_cache(
        st_ycrv, "Transfer", YCRV['ST_YCRV_DEPLOY_BLOCK'], SNAPSHOT_HEIGHT, f"ST_YCRV@{YCRV['ST_YCRV_DEPLOY_BLOCK']}..{SNAPSHOT_HEIGHT}"
    )
    st_users = extract_addresses(st_logs, "Transfer") if st_logs else cached_st_users
    users.update(st_users)

    # Fetch all unique YBS stakers (cached)
    cached_ybs_users, ybs_logs = scan_events_with_cache(
        ybs, "Staked", YCRV['YBS_DEPLOY_BLOCK'], SNAPSHOT_HEIGHT, f"YBS@{YCRV['YBS_DEPLOY_BLOCK']}..{SNAPSHOT_HEIGHT}"
    )
    ybs_users = extract_addresses(ybs_logs, "Staked") if ybs_logs else cached_ybs_users

    users.update(ybs_users)

    # Calculate constant values once (avoid redundant RPC calls in loop)
    st_ycrv_price_per_share = st_ycrv.pricePerShare(block_identifier=SNAPSHOT_HEIGHT) / 1e18

    # If include_lp is True, calculate LP-related values and fetch LP users now
    ycrv_per_share = None
    ycrv_per_lp = None
    if include_lp:
        ycrv_in_pool = ycrv.balanceOf(YCRV['POOL'], block_identifier=SNAPSHOT_HEIGHT)
        pool = Contract(YCRV['POOL'])
        ycrv_per_lp = ycrv_in_pool / pool.totalSupply(block_identifier=SNAPSHOT_HEIGHT)
        ycrv_per_share = ycrv_per_lp * lp_ycrv_v2.pricePerShare(block_identifier=SNAPSHOT_HEIGHT) / 1e18

        # Fetch all unique lp-yCRVv2 users (cached)
        cached_lp_users, lp_logs = scan_events_with_cache(
            lp_ycrv_v2, "Transfer", YCRV['LP_YCRV_V2_DEPLOY_BLOCK'], SNAPSHOT_HEIGHT, f"LP_YCRV_V2@{YCRV['LP_YCRV_V2_DEPLOY_BLOCK']}..{SNAPSHOT_HEIGHT}"
        )
        lp_users = extract_addresses(lp_logs, "Transfer") if lp_logs else cached_lp_users
        users.update(lp_users)

    # Process users in chunks with multicall for better performance
    user_list = list(users)
    values = {}

    print(f"Processing {len(user_list)} users in chunks of {MULTICALL_CHUNK_SIZE}...")

    for chunk_idx in range(0, len(user_list), MULTICALL_CHUNK_SIZE):
        chunk = user_list[chunk_idx:chunk_idx + MULTICALL_CHUNK_SIZE]
        progress = (chunk_idx + len(chunk)) / len(user_list) * 100
        print(f"  [{progress:5.1f}%] Processing users {chunk_idx+1} to {chunk_idx+len(chunk)} of {len(user_list)}")

        # Fetch all balances for this chunk in a single multicall
        chunk_data = defaultdict(dict)
        with multicall(block_identifier=SNAPSHOT_HEIGHT):
            for user in chunk:
                chunk_data[user]['st_balance'] = st_ycrv.balanceOf(user)
                if include_ajna:
                    chunk_data[user]['borrower_info'] = helper.borrowerInfo(YCRV['AJNA_POOL'], user)
                else:
                    chunk_data[user]['borrower_info'] = (0,)  # Dummy tuple
                chunk_data[user]['ybs_balance'] = ybs.balanceOf(user)
                if include_lp:
                    chunk_data[user]['lp_balance'] = lp_ycrv_v2.balanceOf(user)
                if include_vanilla_ycrv:
                    chunk_data[user]['vanilla_ycrv_balance'] = ycrv.balanceOf(user)

        # Calculate final values for this chunk
        for user in chunk:
            value = 0
            if include_lp:
                value = chunk_data[user]['lp_balance'] * ycrv_per_share
            value += chunk_data[user]['st_balance'] * st_ycrv_price_per_share
            if include_ajna:
                value += chunk_data[user]['borrower_info'][0]  # collateral field
            value += chunk_data[user]['ybs_balance']
            if include_vanilla_ycrv:
                value += chunk_data[user]['vanilla_ycrv_balance']
            values[user] = value

    # Handle Firm (cached)
    if include_firm:
        firm = Contract(YCRV['FIRM_MARKET'])
        cached_firm_users, firm_logs = scan_events_with_cache(
            firm, "CreateEscrow", YCRV['FIRM_MARKET_DEPLOY_BLOCK'], SNAPSHOT_HEIGHT, f"FIRM_MARKET@{YCRV['FIRM_MARKET_DEPLOY_BLOCK']}..{SNAPSHOT_HEIGHT}"
        )
        # Note: We don't use the users here, we process escrow mappings from logs directly
        escrows_processed = 0
        for log in firm_logs:
            args = log.get('args') if hasattr(log, 'get') else getattr(log, 'args', None)
            escrow = args.get('escrow') if args else None
            user = args.get('user') if args else None
            if not escrow or not user:
                continue
            value = values.get(escrow, 0)
            if value == 0:
                continue
            if escrow in values:
                del values[escrow]
            values[user] = values.get(user, 0) + value
            escrows_processed += 1
        print(f"Processed {escrows_processed} Firm escrows")
    else:
        print("Skipping FIRM positions (include_firm=False)")

    if include_lp:
        # Handle Curve Gauge direct deposits (cached)
        curve_gauge = Contract(YCRV['CURVE_GAUGE'])
        cached_gauge_users, gauge_logs = scan_events_with_cache(
            curve_gauge, "Transfer", YCRV['CURVE_GAUGE_DEPLOY_BLOCK'], SNAPSHOT_HEIGHT, f"CURVE_GAUGE@{YCRV['CURVE_GAUGE_DEPLOY_BLOCK']}..{SNAPSHOT_HEIGHT}"
        )
        gauge_users = extract_addresses(gauge_logs, "Transfer") if gauge_logs else cached_gauge_users
        # Filter out voters
        gauge_users = {u for u in gauge_users if u not in [YCRV['CONVEX_VOTER'], YCRV['YEARN_VOTER']]}

        # Handle veYFI Gauge (cached)
        veyfi_gauge = Contract(YCRV['VEYFI_GAUGE'])
        cached_veyfi_users, veyfi_logs = scan_events_with_cache(
            lp_ycrv_v2, "Transfer", YCRV['YGAUGE_DEPLOY_BLOCK'], SNAPSHOT_HEIGHT, f"LP_YCRV_V2_VEYFI@{YCRV['YGAUGE_DEPLOY_BLOCK']}..{SNAPSHOT_HEIGHT}",
            search_topics={'receiver': YCRV['VEYFI_GAUGE']}
        )
        veyfi_users = extract_addresses(veyfi_logs, "Transfer") if veyfi_logs else cached_veyfi_users

        # Handle SD Vault (cached)
        sd_gauge = Contract(YCRV['SD_GAUGE'])
        cached_sd_users, sd_logs = scan_events_with_cache(
            lp_ycrv_v2, "Transfer", YCRV['SD_VAULT_DEPLOY_BLOCK'], SNAPSHOT_HEIGHT, f"LP_YCRV_V2_SD@{YCRV['SD_VAULT_DEPLOY_BLOCK']}..{SNAPSHOT_HEIGHT}",
            search_topics={'receiver': YCRV['SD_VAULT']}
        )
        sd_users = extract_addresses(sd_logs, "Transfer") if sd_logs else cached_sd_users

        # Handle Convex (cached)
        convex_deposit = Contract(YCRV['CONVEX_DEPOSIT'])
        reward = Contract(YCRV['CONVEX_REWARD_POOL'])
        cached_convex_users, convex_logs = scan_events_with_cache(
            convex_deposit, "Deposited", YCRV['CONVEX_POOL_DEPLOY_BLOCK'], SNAPSHOT_HEIGHT, f"CONVEX_DEPOSIT@{YCRV['CONVEX_POOL_DEPLOY_BLOCK']}..{SNAPSHOT_HEIGHT}"
        )
        # Filter for specific pool (poolid=184)
        # Note: Cache doesn't filter by poolid, so we must always filter
        if convex_logs:
            # Have new logs - extract all users first, then filter by poolid
            all_convex_users = extract_addresses(convex_logs, "Deposited")
            # Now filter for the specific pool
            filtered_users = set()
            for log in convex_logs:
                args = log.get('args') if hasattr(log, 'get') else log.args
                poolid = args.get('poolid') if args else None
                if poolid == YCRV['CONVEX_PID']:
                    user = args.get('user') if args else None
                    if user:
                        filtered_users.add(user)
            convex_users = filtered_users
        else:
            # Cache hit with no new logs - use cached users
            # Note: cached users already had poolid filtering applied in previous runs
            convex_users = cached_convex_users

        # Collect all LP users with their source types
        all_lp_users = []
        all_lp_users.extend([('curve', user) for user in gauge_users])
        all_lp_users.extend([('veyfi', user) for user in veyfi_users])
        all_lp_users.extend([('sd', user) for user in sd_users])
        all_lp_users.extend([('convex', user) for user in convex_users])

        print(f"Processing {len(all_lp_users)} LP positions (Curve:{len(gauge_users)}, veYFI:{len(veyfi_users)}, SD:{len(sd_users)}, Convex:{len(convex_users)})...")

        # Process LP users in chunks with multicall
        LP_CHUNK_SIZE = 500
        lp_balances = {}

        for chunk_idx in range(0, len(all_lp_users), LP_CHUNK_SIZE):
            chunk = all_lp_users[chunk_idx:chunk_idx + LP_CHUNK_SIZE]
            progress = (chunk_idx + len(chunk)) / len(all_lp_users) * 100
            print(f"  [{progress:5.1f}%] Processing LP users {chunk_idx+1} to {chunk_idx+len(chunk)} of {len(all_lp_users)}")

            # Fetch balances for this chunk
            with multicall(block_identifier=SNAPSHOT_HEIGHT):
                for source, user in chunk:
                    if source == 'curve':
                        lp_balances[(source, user)] = curve_gauge.balanceOf(user)
                    elif source == 'veyfi':
                        lp_balances[(source, user)] = veyfi_gauge.balanceOf(user)
                    elif source == 'sd':
                        lp_balances[(source, user)] = sd_gauge.balanceOf(user)
                    elif source == 'convex':
                        lp_balances[(source, user)] = reward.balanceOf(user)

        # Process all results
        for (source, user), balance in lp_balances.items():
            if source == 'curve':
                value = balance * ycrv_per_lp
            elif source in ['veyfi', 'sd']:
                value = balance * ycrv_per_share
            elif source == 'convex':
                value = balance * ycrv_per_lp

            if value > 0:
                print(f'{source} user', user, value/1e18)
                values[user] = values.get(user, 0) + value


    # Handle Partner Wallets
    for wallet in [
        '0x71E47a4429d35827e0312AA13162197C23287546', # Threshold
        '0x65bb797c2B9830d891D87288F029ed8dACc19705', # Stargate
    ]:
        value = ycrv.balanceOf(wallet, block_identifier=SNAPSHOT_HEIGHT)
        values[wallet] = values.get(wallet, 0) + value

    # Handle Summer proxies with multicall
    guard = Contract(YCRV['SUMMER_GUARD'])
    CHUNK_SIZE = 500
    account_list = list(values.keys())  # Create list AFTER partner wallets added

    print(f"Processing Summer proxy ownership for {len(account_list)} accounts in chunks...")
    proxies_consolidated = 0
    for chunk_idx in range(0, len(account_list), CHUNK_SIZE):
        chunk = account_list[chunk_idx:chunk_idx + CHUNK_SIZE]

        # Fetch all owners for this chunk
        owners = {}
        with multicall(block_identifier=SNAPSHOT_HEIGHT):
            for account in chunk:
                owners[account] = guard.owners(account)

        # Process results
        for account in chunk:
            owner = owners[account]
            if owner != ZERO_ADDRESS:
                value = values.get(account, 0)
                values[owner] = values.get(owner, 0) + value
                values.pop(account, None)  # Remove proxy after transferring to owner
                proxies_consolidated += 1
    print(f"Consolidated {proxies_consolidated} Summer proxy accounts")

    FOUR_A = '0x4444AAAACDBa5580282365e25b16309Bd770ce4a'
    # Handle re-mappings
    contracts = []
    remappings = {
        YCRV['TREASURY']: FOUR_A,
        YCRV['YCHAD']: FOUR_A,
        '0xac580302548FCCBBf00020de20C3A8AA516821AD': FOUR_A, # Split wallet
        '0x1B7e6fB817112b036EAa4AE85479fF1C2E9330A2': FOUR_A, # Swapper
        '0x4E6Ae791Cc33120d72392f2449DBb91dEc6bf694': FOUR_A, # Swapper 2
        '0x476C56cbBC3643D675cf656Fe24349D47AF0471f': FOUR_A, # Swapper 3
        '0x0E1b2d617834994A74C14f255B56eF0b1100F853': FOUR_A, # Swapper 4

        # Any more users that need a remapping?
    }
    remappings_applied = 0
    for user, value in list(values.items()):
        if user in remappings:
            del values[user]
            target = remappings[user]
            values[target] = values.get(target, 0) + value
            remappings_applied += 1
    print(f"Applied {remappings_applied} remappings")

    # Remove Ignore List
    REMOVAL_LIST = [
        YCRV['ST_YCRV'],
        YCRV['VEYFI_GAUGE'],
        YCRV['CURVE_GAUGE'],
        YCRV['AJNA_POOL'],
        YCRV['LP_YCRV_V2'],
        YCRV['LP_RECOVER_STRATEGY'],
        YCRV['SD_LOCKER'],
        YCRV['YBS'],
        YCRV['YBS_STRATEGY'],
        ZERO_ADDRESS,
    ]
    for item in REMOVAL_LIST:
        values.pop(item, None)

    # Batch all withdrawalQueue calls with multicall
    print("Fetching withdrawal queue strategies...")
    strategies = {}
    with multicall(block_identifier=SNAPSHOT_HEIGHT):
        for i in range(0, 100):
            strategies[i] = lp_ycrv_v2.withdrawalQueue(i)

    # Remove strategies from values
    for i, strat in strategies.items():
        if strat == ZERO_ADDRESS:
            break
        values.pop(strat, None)

    if include_untokenized:
        # Handle untokenized
        total = sum(values.values())
        untokenized = (
            ve.balanceOf(YCRV['YEARN_VOTER'], block_identifier=SNAPSHOT_HEIGHT) - 
            total
        )
        values[YCRV['YCHAD']] = values.get(YCRV['YCHAD'], 0) + untokenized # Yearn controls all untokenized amounts

    values = dict(sorted(values.items(), key=lambda item: item[1], reverse=True))   # Sort list by highest value
    values = {k: int(float(v)) for k, v in values.items()}                          # Convert to int
    values = {k: v for k, v in values.items() if v >= MIN_AMOUNT}                   # Remove anything less than min

    # Discover contracts (identify addresses with bytecode that aren't EOF format)
    for user, val in list(values.items()):
        data = web3.eth.get_code(user).hex()
        if data == '0x' or data == '' or data.startswith(EOF_BYTECODE_PREFIX) or data.startswith(EOF_BYTECODE_PREFIX_NO_PREFIX):
            continue
        print(user, val/1e18)
        contracts.append(user)
    print(f"Discovered {len(contracts)} contract addresses with balances")

    values = {k: v / 1e18 for k, v in values.items()}
    total = sum(values.values())

    # Get block timestamp
    block_timestamp = web3.eth.get_block(SNAPSHOT_HEIGHT)['timestamp']

    # Get drop name and snapshot dir from config (already loaded at function start)
    drop_name = config.get('drop_name', DropConfig.DROP_NAME)
    snapshot_dir = config.get('snapshot_dir', DropConfig.SNAPSHOT_DIR)

    # Build output with metadata
    output = {
        'metadata': {
            'drop_name': drop_name,
            'snapshot_height': SNAPSHOT_HEIGHT,
            'block_timestamp': block_timestamp,
            'include_lp': include_lp,
            'include_untokenized': include_untokenized,
            'include_firm': include_firm,
            'include_ajna': include_ajna,
            'include_vanilla_ycrv': include_vanilla_ycrv,
            'min_amount_wei': str(MIN_AMOUNT),
            'min_amount': MIN_AMOUNT / 1e18,  # Also store decimal for convenience
            'generated_at': datetime.utcnow().isoformat() + 'Z',
        },
        'total': total,
        'num_recipients': len(values),
        'values': values,
    }
    print("TOTAL -->",total)

    # Write to json with block-specific filename
    os.makedirs(snapshot_dir, exist_ok=True)
    output_file = DropConfig.get_snapshot_file(SNAPSHOT_HEIGHT)
    with open(output_file, 'w') as f:
        dump(output, f, indent=2)