import json
from brownie import web3
from itertools import zip_longest
from eth_utils import encode_hex
from eth_abi.packed import encode_packed
from config import Config

class MerkleTree:
    def __init__(self, elements):
        self.elements = sorted(set(web3.keccak(hexstr=el) for el in elements))
        self.layers = MerkleTree.get_layers(self.elements)

    @property
    def root(self):
        return self.layers[-1][0]

    def get_proof(self, el):
        el = web3.keccak(hexstr=el)
        idx = self.elements.index(el)
        proof = []
        for layer in self.layers:
            pair_idx = idx + 1 if idx % 2 == 0 else idx - 1
            if pair_idx < len(layer):
                proof.append(encode_hex(layer[pair_idx]))
            idx //= 2
        return proof

    @staticmethod
    def get_layers(elements):
        layers = [elements]
        while len(layers[-1]) > 1:
            layers.append(MerkleTree.get_next_layer(layers[-1]))
        return layers

    @staticmethod
    def get_next_layer(elements):
        return [
            MerkleTree.combined_hash(a, b) for a, b in zip_longest(elements[::2], elements[1::2])
        ]

    @staticmethod
    def combined_hash(a, b):
        if a is None:
            return b
        if b is None:
            return a
        return web3.keccak(b"".join(sorted([a, b])))
    
def create_merkle(user_amount_data, total_distribution, alloc_type):
    # Convert values to integers and calculate ratio using integer division
    total_amounts = sum(user_amount_data.values())
    
    # Calculate amounts using integer multiplication first, then division
    user_amount_data = {
        k.lower(): (v * total_distribution) // total_amounts 
        for k, v in user_amount_data.items()
    }
    
    addresses = sorted(user_amount_data, key=lambda k: user_amount_data[k], reverse=True)
    while sum(user_amount_data.values()) < total_distribution:
        diff = total_distribution - sum(user_amount_data.values())
        user_amount_data[addresses[len(addresses) - 1]] += diff
    assert sum(user_amount_data.values()) == total_distribution
    
    elements = [
        (account, index, user_amount_data[account]) for index, account in enumerate(addresses)
    ]
    nodes = [encode_hex(encode_packed(["address", "uint", "uint"], el)) for el in elements]
    tree = MerkleTree(nodes)

    distribution = {
        "merkle_root": encode_hex(tree.root),
        "token_total": sum(user_amount_data.values()),
        "claims": {
            web3.to_checksum_address(user): {
                "index": index,
                "amount": str(amount),
                "proof": tree.get_proof(nodes[index]),
            }
            for user, index, amount in elements
        },
    }

    # Write the distribution data to a JSON file
    with open(Config.get_merkle_file(alloc_type), 'w') as json_file:
        json.dump(distribution, json_file, indent=4)
    print(f'Distribution successfully written for {len(distribution["claims"])} users')
    print(f"base merkle root: {encode_hex(tree.root)}")
    return distribution