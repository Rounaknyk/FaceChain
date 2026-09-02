from __future__ import annotations

from web3 import Web3


PREFIX = b"FACECHAIN_V1:"


def commit_hash(digest: str, rpc_url: str, private_key: str) -> dict:
    if len(digest) != 64:
        raise ValueError("Expected a SHA-256 hex digest")
    web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 60}))
    if not web3.is_connected():
        raise ConnectionError("Could not connect to the Sepolia RPC endpoint")
    account = web3.eth.account.from_key(private_key)
    transaction = {
        "from": account.address,
        "to": account.address,
        "value": 0,
        "data": Web3.to_hex(PREFIX + bytes.fromhex(digest)),
        "nonce": web3.eth.get_transaction_count(account.address),
        "chainId": web3.eth.chain_id,
        "gas": 30_000,
        "maxPriorityFeePerGas": web3.to_wei(1, "gwei"),
    }
    if transaction["chainId"] != 11155111:
        raise RuntimeError(f"Refusing to write: expected Sepolia chain 11155111, got {transaction['chainId']}")
    transaction["maxFeePerGas"] = web3.eth.get_block("latest")["baseFeePerGas"] * 2 + transaction["maxPriorityFeePerGas"]
    signed = account.sign_transaction(transaction)
    tx_hash = web3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = web3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    if receipt.status != 1:
        raise RuntimeError(f"Blockchain transaction failed: {tx_hash.hex()}")
    return {
        "network": "Ethereum Sepolia",
        "chain_id": transaction["chainId"],
        "transaction_hash": tx_hash.hex(),
        "block_number": receipt.blockNumber,
        "committer": account.address,
        "explorer_url": f"https://sepolia.etherscan.io/tx/{tx_hash.hex()}",
    }


def verify_hash(digest: str, transaction_hash: str, rpc_url: str) -> dict:
    web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 60}))
    tx = web3.eth.get_transaction(transaction_hash)
    expected = Web3.to_hex(PREFIX + bytes.fromhex(digest)).lower()
    actual = tx["input"].hex().lower()
    if not actual.startswith("0x"):
        actual = "0x" + actual
    return {
        "valid": actual == expected and tx["chainId"] == 11155111,
        "block_number": tx.get("blockNumber"),
        "committer": tx["from"],
        "network": "Ethereum Sepolia",
    }
