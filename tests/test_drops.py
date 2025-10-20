from brownie import Contract, interface, accounts, chain, reverts, web3
import time


def test_drops(drops, dai, create_drop):
    # Create a drop using helper with defaults
    amount = 100_000 * 10**18
    drop_id, tx = create_drop(amount=amount)

    # Check drop was created
    assert drops.dropCount() == 1
    assert drop_id == 0
    drop = drops.drops(0)
    assert drop[0] == dai.address  # token
    assert drop[3] == amount  # totalAmount
    assert drop[4] == 0  # claimedAmount


def test_owner_access_control(drops, dai, gov, accounts, create_drop):
    # Test only owner can create drops
    amount = 1000 * 10**18
    duration = 86400
    merkle_root = "0x" + "00" * 32

    with reverts():
        drops.createDrop(dai.address, 0, duration, amount, merkle_root, {"from": accounts[2]})

    # Create a drop as owner (should succeed)
    drop_id, tx = create_drop()

    # Test only owner can set merkle root
    with reverts():
        drops.setMerkleRoot(0, "0x1234" + "00" * 30, {"from": accounts[2]})
    drops.setMerkleRoot(0, "0x1234" + "00" * 30, {"from": gov})

def test_recover_tokens(drops, dai, gov, create_drop, web3):
    # Create drop with short expiry
    amount = 100_000 * 10**18
    duration = 100
    drop_id, tx = create_drop(amount=amount, duration=duration)

    chain.sleep(200)
    
    gov_balance_before = dai.balanceOf(gov)
    drops.recoverExpiredTokens(drop_id, {"from": gov})
    gov_balance_after = dai.balanceOf(gov)

    assert gov_balance_after - gov_balance_before == amount

def test_set_merkle_root(drops, dai, gov, create_drop):
    # Create drop with default (zero) merkle root
    amount = 1000 * 10**18
    drop_id, tx = create_drop(amount=amount)

    # Set merkle root
    new_root = "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
    drops.setMerkleRoot(drop_id, new_root, {"from": gov})

    # Check it was set
    drop = drops.drops(drop_id)
    assert drop[5] == new_root.lower()

def test_claim(drops, dai, gov, accounts, create_drop):
    # Setup drop with merkle root
    amount = 1000 * 10**18
    merkle_root = "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
    drop_id, tx = create_drop(amount=amount, merkle_root=merkle_root)

    # Simple test - just verify the claim reverts without valid proof
    account = accounts[2]

    # Try to claim with invalid proof (should fail)
    with reverts("invalid proof"):
        drops.claim(drop_id, account, account, 100 * 10**18, [], 0, {"from": account})

def test_delegate(drops, gov, accounts):
    # Set delegate
    account = accounts[1]
    delegate = accounts[2]
    tx = drops.setDelegate(account, delegate, {"from": account})
    assert drops.delegates(account) == delegate
    # Owner can also set delegate for any account
    drops.setDelegate(accounts[3], accounts[4], {"from": gov})


def test_yb_claim_production_data(drops, yb_token, yb_merkle_data, dai_whale, gov):
    """Test claiming with actual production YB merkle data"""
    # Get merkle root and total from production data
    merkle_root = yb_merkle_data['merkle_root']
    total_amount = int(yb_merkle_data['token_total'])

    # Fund drops contract
    yb_token.transfer(drops.address, total_amount, {"from": dai_whale})

    # Create drop with production merkle root
    duration = 86400 * 30
    drop_id = drops.dropCount()
    drops.createDrop(yb_token.address, 0, duration, total_amount, merkle_root, {"from": gov})

    # Pick first 3 addresses from claims to test
    test_accounts = list(yb_merkle_data['claims'].keys())[:3]

    for account in test_accounts:
        claim_data = yb_merkle_data['claims'][account]
        amount = int(claim_data['amount'])
        index = claim_data['index']
        proof = claim_data['proof']

        # Impersonate account for testing
        balance_before = yb_token.balanceOf(account)

        # Claim tokens
        drops.claim(drop_id, account, account, amount, proof, index, {"from": account})

        # Verify claim succeeded
        assert drops.hasClaimed(account, drop_id) == True
        balance_after = yb_token.balanceOf(account)
        assert balance_after - balance_before == amount


def test_yb_double_claim_protection(drops, yb_token, yb_merkle_data, dai_whale, gov):
    """Test that users cannot claim twice"""
    merkle_root = yb_merkle_data['merkle_root']
    total_amount = int(yb_merkle_data['token_total'])

    # Setup drop
    yb_token.transfer(drops.address, total_amount, {"from": dai_whale})
    drop_id = drops.dropCount()
    drops.createDrop(yb_token.address, 0, 86400 * 30, total_amount, merkle_root, {"from": gov})

    # Get first claim data
    account = list(yb_merkle_data['claims'].keys())[0]
    claim_data = yb_merkle_data['claims'][account]
    amount = int(claim_data['amount'])
    index = claim_data['index']
    proof = claim_data['proof']

    # First claim succeeds
    drops.claim(drop_id, account, account, amount, proof, index, {"from": account})

    # Second claim should fail
    with reverts("already claimed"):
        drops.claim(drop_id, account, account, amount, proof, index, {"from": account})


def test_yb_invalid_proof(drops, yb_token, yb_merkle_data, dai_whale, gov):
    """Test that invalid merkle proofs are rejected"""
    merkle_root = yb_merkle_data['merkle_root']
    total_amount = int(yb_merkle_data['token_total'])

    # Setup drop
    yb_token.transfer(drops.address, total_amount, {"from": dai_whale})
    drop_id = drops.dropCount()
    drops.createDrop(yb_token.address, 0, 86400 * 30, total_amount, merkle_root, {"from": gov})

    # Get real claim data but use wrong proof
    account = list(yb_merkle_data['claims'].keys())[0]
    claim_data = yb_merkle_data['claims'][account]
    amount = int(claim_data['amount'])
    index = claim_data['index']

    # Use empty proof (make proof invalid by moving last item to front)
    last_item = claim_data['proof'][-1]
    wrong_proof = [last_item] + claim_data['proof'][:-1]

    with reverts("invalid proof"):
        drops.claim(drop_id, account, account, amount, wrong_proof, index, {"from": account})
