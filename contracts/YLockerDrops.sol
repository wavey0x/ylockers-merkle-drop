// SPDX-License-Identifier: MIT
pragma solidity 0.8.28;

import { IERC20 } from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import { SafeERC20 } from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import { MerkleProof } from "@openzeppelin/contracts/utils/cryptography/MerkleProof.sol";
import { Ownable } from "@openzeppelin/contracts/access/Ownable.sol";

contract YlockerDrops is Ownable {
    using SafeERC20 for IERC20;

    uint256 public constant MAX_DESCRIPTION_BYTES = 384;

    uint256 public dropCount;
    mapping(address account => address delegate) public delegates;
    mapping(uint256 id => Drop drop) public drops;
    mapping(address account => mapping(uint256 dropId => bool hasClaimed)) public hasClaimed;

    struct Drop {
        address token;
        uint40 startsAt;
        uint40 expiresAt;
        uint256 totalAmount;
        uint256 claimedAmount;
        bytes32 merkleRoot;
        string description;
    }

    event DropCreated(uint256 indexed dropId, address indexed token, uint256 startsAt, uint256 expiresAt, uint256 totalAmount);
    event MerkleRootSet(uint256 indexed dropId, bytes32 merkleRoot);
    event Claimed(uint256 indexed dropId, address indexed account, address indexed recipient, uint256 amount);
    event ExpiredTokensRecovered(uint256 indexed dropId, address indexed token, uint256 amount);
    event DelegateSet(address indexed account, address indexed delegate);
    event DropDescriptionSet(uint256 indexed dropId, string description);

    constructor(address _owner) Ownable(_owner) {}

    function claim(
        uint256 _dropId,
        address _account,
        address _recipient,
        uint256 _amount,
        bytes32[] calldata _proof,
        uint256 _index
    ) external {
        require(msg.sender == _account || msg.sender == delegates[_account], "!authorized");
        Drop storage drop = drops[_dropId];
        bytes32 _root = drop.merkleRoot;
        require(_root != bytes32(0), "root not set");
        require(drop.startsAt <= block.timestamp, "!started");
        require(drop.expiresAt >= block.timestamp, "expired");
        require(!hasClaimed[_account][_dropId], "already claimed");
        bytes32 node = keccak256(abi.encodePacked(_account, _index, _amount));
        require(MerkleProof.verifyCalldata(
            _proof,
            _root,
            node
        ), "invalid proof");
        hasClaimed[_account][_dropId] = true;
        drop.claimedAmount += _amount;
        emit Claimed(_dropId, _account, _recipient, _amount);
        IERC20(drop.token).safeTransfer(_recipient, _amount);
    }

    /**
        @notice Create a new drop
        @param _token Token to be distributed
        @param _startTime Start timestamp for claims.
        @param _duration Duration of the drop in seconds
        @param _totalAmount Total amount of tokens to be distributed
        @param _merkleRoot Merkle root for the drop
    */
    function createDrop(string calldata _description, address _token, uint256 _startTime, uint256 _duration, uint256 _totalAmount, bytes32 _merkleRoot) external onlyOwner {
        require(bytes(_description).length <= MAX_DESCRIPTION_BYTES, "Description too long");
        if (_startTime == 0) _startTime = block.timestamp;
        require(_startTime >= block.timestamp);
        require(_totalAmount > 0, "totalAmount must be greater than 0");
        require(IERC20(_token).balanceOf(address(this)) >= _totalAmount, "not funded");
        require(_duration > 0, "duration must be greater than 0");
        uint256 _dropId = dropCount++;
        drops[_dropId] = Drop(_token, uint40(_startTime), uint40(block.timestamp + _duration), _totalAmount, 0, _merkleRoot, _description);
        emit DropCreated(_dropId, _token, uint40(_startTime), uint40(block.timestamp + _duration), _totalAmount);
        if (_merkleRoot != bytes32(0)) {
            emit MerkleRootSet(_dropId, _merkleRoot);
        }
    }

    /**
        @notice Set the merkle root for a drop
        @param _dropId ID of the drop
        @param _root Merkle root for the drop
    */
    function setMerkleRoot(uint256 _dropId, bytes32 _root) external onlyOwner {
        drops[_dropId].merkleRoot = _root;
        emit MerkleRootSet(_dropId, _root);
    }

    function recoverExpiredTokens(uint256 _dropId) external onlyOwner {
        Drop storage drop = drops[_dropId];
        require(block.timestamp > drop.expiresAt, "not expired");
        require(drop.claimedAmount < drop.totalAmount, "fully claimed");
        uint256 _amount = drop.totalAmount - drop.claimedAmount;
        IERC20(drop.token).safeTransfer(owner(), _amount);
        emit ExpiredTokensRecovered(_dropId, drop.token, _amount);
    }

    /**
        @notice Set a delegate for an account, allowing them to claim on behalf of the account.
        @dev Can only be called by the account itself or the owner.
        @param _account Account to set the delegate for.
        @param _delegate Delegate to set for the account
    */
    function setDelegate(address _account, address _delegate) external {
        require(msg.sender == _account || msg.sender == owner(), "not authorized");
        delegates[_account] = _delegate;
        emit DelegateSet(_account, _delegate);
    }

    function setDropDescription(uint256 _dropId, string calldata _description) external onlyOwner {
        drops[_dropId].description = _description;
        emit DropDescriptionSet(_dropId, _description);
    }
}