// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title RAYA Evidence Anchor
/// @notice Tamper-evident anchoring for visual-evidence verification records.
///
/// @dev The contract is deliberately small, and the things it does *not* do are
///      as much a part of the design as the things it does:
///
///      - No owner, no admin, no pause, no upgrade path. There is no privileged
///        key that could rewrite history, because a mutable anchor is not an
///        anchor.
///      - No token, no fees, no access control. Anchoring is open; the record
///        stores who submitted it and lets readers judge that for themselves.
///      - Records are write-once. `anchor` reverts on an id that already
///        exists rather than overwriting, so a confirmed anchor is final.
///
///      What is stored is only hashes, a content identifier and a scalar score.
///      No image, no face, and no biometric template is ever written on chain.
///      That is a hard privacy boundary: this data is public and permanent.
contract RayaEvidenceAnchor {
    /// @param evidenceHash SHA-256 of the canonical evidence JSON.
    /// @param inputHash    SHA-256 of the user-supplied input image bytes.
    /// @param sourceHash   SHA-256 of the independently retrieved source image.
    /// @param cid          IPFS content identifier of the evidence bundle.
    /// @param similarityBp Face similarity in basis points (0.8300 -> 8300).
    ///                     Signed, because cosine similarity is defined on
    ///                     [-1, 1] and clamping would misreport a real value.
    /// @param anchoredAt   Block timestamp at which the record was written.
    /// @param submitter    Account that submitted the anchor.
    struct Record {
        bytes32 evidenceHash;
        bytes32 inputHash;
        bytes32 sourceHash;
        string cid;
        int32 similarityBp;
        uint64 anchoredAt;
        address submitter;
    }

    /// @dev keccak256(verificationId) => record.
    mapping(bytes32 => Record) private _records;

    /// @dev evidenceHash => verification id key, for reverse lookup. This is
    ///      what makes an integrity check possible from the evidence file
    ///      alone, without knowing the run it came from.
    mapping(bytes32 => bytes32) private _byEvidenceHash;

    bytes32[] private _ids;

    event EvidenceAnchored(
        bytes32 indexed idKey,
        bytes32 indexed evidenceHash,
        string verificationId,
        bytes32 inputHash,
        bytes32 sourceHash,
        string cid,
        int32 similarityBp,
        address indexed submitter,
        uint64 anchoredAt
    );

    error AlreadyAnchored(bytes32 idKey);
    error UnknownRecord(bytes32 idKey);
    error EmptyEvidenceHash();
    error EmptyVerificationId();

    /// @notice Anchor one verification record.
    /// @param verificationId Human-readable run id, e.g. "VER-20260905-A1B2C3".
    /// @return idKey The keccak256 key the record is stored under.
    function anchor(
        string calldata verificationId,
        bytes32 evidenceHash,
        bytes32 inputHash,
        bytes32 sourceHash,
        string calldata cid,
        int32 similarityBp
    ) external returns (bytes32 idKey) {
        if (bytes(verificationId).length == 0) revert EmptyVerificationId();
        if (evidenceHash == bytes32(0)) revert EmptyEvidenceHash();

        idKey = keccak256(bytes(verificationId));
        if (_records[idKey].evidenceHash != bytes32(0)) revert AlreadyAnchored(idKey);

        _records[idKey] = Record({
            evidenceHash: evidenceHash,
            inputHash: inputHash,
            sourceHash: sourceHash,
            cid: cid,
            similarityBp: similarityBp,
            anchoredAt: uint64(block.timestamp),
            submitter: msg.sender
        });
        _byEvidenceHash[evidenceHash] = idKey;
        _ids.push(idKey);

        emit EvidenceAnchored(
            idKey,
            evidenceHash,
            verificationId,
            inputHash,
            sourceHash,
            cid,
            similarityBp,
            msg.sender,
            uint64(block.timestamp)
        );
    }

    /// @notice Read a record back by verification id. This is the call the
    ///         integrity check makes after a transaction confirms -- RAYA does
    ///         not treat "transaction submitted" as success.
    function getRecord(string calldata verificationId) external view returns (Record memory) {
        bytes32 idKey = keccak256(bytes(verificationId));
        Record memory record = _records[idKey];
        if (record.evidenceHash == bytes32(0)) revert UnknownRecord(idKey);
        return record;
    }

    /// @notice Read a record by its precomputed key.
    function getRecordByKey(bytes32 idKey) external view returns (Record memory) {
        Record memory record = _records[idKey];
        if (record.evidenceHash == bytes32(0)) revert UnknownRecord(idKey);
        return record;
    }

    /// @notice Single-call integrity check: does the anchored hash for this id
    ///         still equal the hash the caller computed locally?
    function verifyEvidence(string calldata verificationId, bytes32 expectedHash)
        external
        view
        returns (bool matches, bytes32 storedHash)
    {
        storedHash = _records[keccak256(bytes(verificationId))].evidenceHash;
        matches = storedHash != bytes32(0) && storedHash == expectedHash;
    }

    /// @notice Look up which run anchored a given evidence hash.
    function idKeyForEvidence(bytes32 evidenceHash) external view returns (bytes32) {
        return _byEvidenceHash[evidenceHash];
    }

    function isAnchored(string calldata verificationId) external view returns (bool) {
        return _records[keccak256(bytes(verificationId))].evidenceHash != bytes32(0);
    }

    function totalRecords() external view returns (uint256) {
        return _ids.length;
    }

    function idKeyAt(uint256 index) external view returns (bytes32) {
        return _ids[index];
    }
}
