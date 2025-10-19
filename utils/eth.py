from brownie import web3
from datetime import datetime


def block_to_date(b):
    time = web3.eth.get_block(b)['timestamp']
    return datetime.fromtimestamp(time)


def closest_block_after_timestamp(timestamp: int) -> int:
    return _closest_block_after_timestamp(timestamp)


def closest_block_before_timestamp(timestamp: int) -> int:
    return closest_block_after_timestamp(timestamp) - 1


def _closest_block_after_timestamp(timestamp: int) -> int:
    height = web3.eth.block_number
    lo, hi = 0, height

    while hi - lo > 1:
        mid = lo + (hi - lo) // 2
        if get_block_timestamp(mid) > timestamp:
            hi = mid
        else:
            lo = mid

    if get_block_timestamp(hi) < timestamp:
        raise Exception("timestamp is in the future")
    return hi


def get_block_timestamp(height):
    return web3.eth.get_block(height)['timestamp']


def timestamp_to_date_string(ts):
    return datetime.utcfromtimestamp(ts).strftime("%m/%d/%Y, %H:%M:%S")


def timestamp_to_string(ts):
    dt = datetime.utcfromtimestamp(ts).strftime("%m/%d/%Y, %H:%M:%S")
    return dt


def contract_creation_block(address):
    """
    Find contract creation block using binary search.
    NOTE Requires access to historical state. Doesn't account for CREATE2 or SELFDESTRUCT.
    """
    lo = 0
    hi = end = web3.eth.block_number

    while hi - lo > 1:
        mid = lo + (hi - lo) // 2
        code = web3.eth.get_code(address, block_identifier=mid)
        if code:
            hi = mid
        else:
            lo = mid
    return hi if hi != end else None


def get_logs_chunked(contract, event_name, start_block=0, end_block=0, chunk_size=100_000):
    try:
        event = getattr(contract.events, event_name)
    except Exception as e:
        print(f'Contract has no event by the name {event_name}', e)

    if start_block == 0:
        start_block = contract_creation_block(contract.address)
    if end_block == 0:
        end_block = web3.eth.block_number

    logs = []
    while start_block < end_block:
        logs += event.get_logs(fromBlock=start_block, toBlock=min(end_block, start_block + chunk_size))
        start_block += chunk_size

    return logs