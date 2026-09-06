"""ABI for `RayaEvidenceAnchor`.

Kept in Python rather than read from Hardhat build output so the API can talk
to an already-deployed contract without the Node toolchain present. It is
checked against the compiled artifact by `tests/test_contract_abi.py`, so the
two cannot drift apart silently.
"""

RECORD_COMPONENTS = [
    {"name": "evidenceHash", "type": "bytes32"},
    {"name": "inputHash", "type": "bytes32"},
    {"name": "sourceHash", "type": "bytes32"},
    {"name": "cid", "type": "string"},
    {"name": "similarityBp", "type": "int32"},
    {"name": "anchoredAt", "type": "uint64"},
    {"name": "submitter", "type": "address"},
]

RAYA_ANCHOR_ABI = [
    {
        "type": "function",
        "name": "anchor",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "verificationId", "type": "string"},
            {"name": "evidenceHash", "type": "bytes32"},
            {"name": "inputHash", "type": "bytes32"},
            {"name": "sourceHash", "type": "bytes32"},
            {"name": "cid", "type": "string"},
            {"name": "similarityBp", "type": "int32"},
        ],
        "outputs": [{"name": "idKey", "type": "bytes32"}],
    },
    {
        "type": "function",
        "name": "getRecord",
        "stateMutability": "view",
        "inputs": [{"name": "verificationId", "type": "string"}],
        "outputs": [
            {"name": "", "type": "tuple", "components": RECORD_COMPONENTS}
        ],
    },
    {
        "type": "function",
        "name": "getRecordByKey",
        "stateMutability": "view",
        "inputs": [{"name": "idKey", "type": "bytes32"}],
        "outputs": [
            {"name": "", "type": "tuple", "components": RECORD_COMPONENTS}
        ],
    },
    {
        "type": "function",
        "name": "verifyEvidence",
        "stateMutability": "view",
        "inputs": [
            {"name": "verificationId", "type": "string"},
            {"name": "expectedHash", "type": "bytes32"},
        ],
        "outputs": [
            {"name": "matches", "type": "bool"},
            {"name": "storedHash", "type": "bytes32"},
        ],
    },
    {
        "type": "function",
        "name": "idKeyForEvidence",
        "stateMutability": "view",
        "inputs": [{"name": "evidenceHash", "type": "bytes32"}],
        "outputs": [{"name": "", "type": "bytes32"}],
    },
    {
        "type": "function",
        "name": "isAnchored",
        "stateMutability": "view",
        "inputs": [{"name": "verificationId", "type": "string"}],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "type": "function",
        "name": "totalRecords",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "type": "function",
        "name": "idKeyAt",
        "stateMutability": "view",
        "inputs": [{"name": "index", "type": "uint256"}],
        "outputs": [{"name": "", "type": "bytes32"}],
    },
    {
        "type": "event",
        "name": "EvidenceAnchored",
        "anonymous": False,
        "inputs": [
            {"name": "idKey", "type": "bytes32", "indexed": True},
            {"name": "evidenceHash", "type": "bytes32", "indexed": True},
            {"name": "verificationId", "type": "string", "indexed": False},
            {"name": "inputHash", "type": "bytes32", "indexed": False},
            {"name": "sourceHash", "type": "bytes32", "indexed": False},
            {"name": "cid", "type": "string", "indexed": False},
            {"name": "similarityBp", "type": "int32", "indexed": False},
            {"name": "submitter", "type": "address", "indexed": True},
            {"name": "anchoredAt", "type": "uint64", "indexed": False},
        ],
    },
    {"type": "error", "name": "AlreadyAnchored", "inputs": [{"name": "idKey", "type": "bytes32"}]},
    {"type": "error", "name": "UnknownRecord", "inputs": [{"name": "idKey", "type": "bytes32"}]},
    {"type": "error", "name": "EmptyEvidenceHash", "inputs": []},
    {"type": "error", "name": "EmptyVerificationId", "inputs": []},
]
