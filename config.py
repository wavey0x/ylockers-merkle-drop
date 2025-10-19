from dataclasses import dataclass

class ContractAddresses:
    VECRV = '0x5f3b5DfEb7B28CDbD7FAba78963EE202a494e2A2'
    YEARN_VOTER = '0xF147b8125d2ef93FB6965Db97D6746952a133934'
    YCRV = '0xFCc5c47bE19d06BF83eB04298b026F81069ff65b'
    ST_YCRV = '0x27B5739e22ad9033bcBf192059122d163b60349D'
    LP_YCRV_V2 = '0x6E9455D109202b426169F0d8f01A3332DAE160f3'
    VEYFI_GAUGE = '0x107717C98C8125A94D3d2Cc82b86a1b705f3A27C'
    CURVE_GAUGE = '0xeebc06d495c96e57542a6d829184a907a02ef602'
    POOL = '0x99f5aCc8EC2Da2BC0771c32814EFF52b712de1E5'
    YCHAD = '0xFEB4acf3df3cDEA7399794D0869ef76A6EfAff52'

class Config:
    # Directory structure
    DATA_DIR = 'data'
    MERKLE_DIR = f'{DATA_DIR}/merkle'
    SOURCES_DIR = f'{DATA_DIR}/sources'
    CACHE_DIR = f'{DATA_DIR}/cache'
    
    # Cache data files
    USERS_LOCKS_FILE = f'{CACHE_DIR}/user_lock_data.json'
    SUPPLY_DATA_FILE = f'{CACHE_DIR}/supply_data.json'
    
    # Source data files
    TEAM_SPLITS_FILE = f'{SOURCES_DIR}/team_splits.json'
    VICTIM_DATA_FILE = f'{SOURCES_DIR}/victim_data.json'
    PENALTY_DATA_FILE = f'{SOURCES_DIR}/penalty_data.json'
    YCRV_SNAPSHOT_FILE = f'{SOURCES_DIR}/ycrv_snapshot.json'

    # Merkle output files
    YB_DISTRO_FILE = f'{MERKLE_DIR}/yb_distro.json'

    # Constants
    DUST_THRESHOLD = 1e3

    @classmethod
    def get_merkle_file(cls, alloc_type: str) -> str:
        """Returns the path to a merkle data file for a given allocation type"""
        return f'{cls.MERKLE_DIR}/merkle_data_{alloc_type}.json'