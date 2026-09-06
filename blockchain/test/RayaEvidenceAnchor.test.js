const { expect } = require("chai");
const { ethers } = require("hardhat");

/**
 * The properties these tests protect are the ones the product's claims rest on:
 * a record reads back byte-identical, it cannot be overwritten, and a changed
 * evidence hash is detected. If any of those break, "tamper-evident" is a lie.
 */
describe("RayaEvidenceAnchor", function () {
  let contract;
  let owner;
  let other;

  const ID = "VER-20260905-ABCDEF123456";
  const evidenceHash = ethers.keccak256(ethers.toUtf8Bytes("evidence"));
  const inputHash = ethers.keccak256(ethers.toUtf8Bytes("input"));
  const sourceHash = ethers.keccak256(ethers.toUtf8Bytes("source"));
  const CID = "bafkreifzjut3te2nhyekklss27nh3k72ysco7y32koao5eei66wof36n5e";
  const SIMILARITY_BP = 8300;
  const ZERO = "0x" + "0".repeat(64);

  beforeEach(async function () {
    [owner, other] = await ethers.getSigners();
    const Factory = await ethers.getContractFactory("RayaEvidenceAnchor");
    contract = await Factory.deploy();
    await contract.waitForDeployment();
  });

  describe("anchoring", function () {
    it("stores a record that reads back identically", async function () {
      await contract.anchor(ID, evidenceHash, inputHash, sourceHash, CID, SIMILARITY_BP);

      const record = await contract.getRecord(ID);
      expect(record.evidenceHash).to.equal(evidenceHash);
      expect(record.inputHash).to.equal(inputHash);
      expect(record.sourceHash).to.equal(sourceHash);
      expect(record.cid).to.equal(CID);
      expect(record.similarityBp).to.equal(SIMILARITY_BP);
      expect(record.submitter).to.equal(owner.address);
      expect(record.anchoredAt).to.be.greaterThan(0);
    });

    it("emits EvidenceAnchored with the readable verification id", async function () {
      await expect(
        contract.anchor(ID, evidenceHash, inputHash, sourceHash, CID, SIMILARITY_BP)
      )
        .to.emit(contract, "EvidenceAnchored")
        .withArgs(
          ethers.keccak256(ethers.toUtf8Bytes(ID)),
          evidenceHash,
          ID,
          inputHash,
          sourceHash,
          CID,
          SIMILARITY_BP,
          owner.address,
          (value) => value > 0n
        );
    });

    it("accepts a negative similarity", async function () {
      // Cosine similarity is defined on [-1, 1]. Storing it signed means a real
      // measurement is never silently clamped to zero.
      await contract.anchor(ID, evidenceHash, inputHash, sourceHash, CID, -1500);
      const record = await contract.getRecord(ID);
      expect(record.similarityBp).to.equal(-1500);
    });

    it("lets anyone anchor -- there is no privileged key", async function () {
      await contract
        .connect(other)
        .anchor(ID, evidenceHash, inputHash, sourceHash, CID, SIMILARITY_BP);
      const record = await contract.getRecord(ID);
      expect(record.submitter).to.equal(other.address);
    });
  });

  describe("immutability", function () {
    it("refuses to overwrite an existing record", async function () {
      await contract.anchor(ID, evidenceHash, inputHash, sourceHash, CID, SIMILARITY_BP);

      const forged = ethers.keccak256(ethers.toUtf8Bytes("forged"));
      await expect(
        contract.anchor(ID, forged, inputHash, sourceHash, CID, 9900)
      ).to.be.revertedWithCustomError(contract, "AlreadyAnchored");
    });

    it("refuses an overwrite from a different account too", async function () {
      await contract.anchor(ID, evidenceHash, inputHash, sourceHash, CID, SIMILARITY_BP);
      await expect(
        contract.connect(other).anchor(ID, evidenceHash, inputHash, sourceHash, CID, 100)
      ).to.be.revertedWithCustomError(contract, "AlreadyAnchored");
    });

    it("leaves the original intact after a rejected overwrite", async function () {
      await contract.anchor(ID, evidenceHash, inputHash, sourceHash, CID, SIMILARITY_BP);
      const forged = ethers.keccak256(ethers.toUtf8Bytes("forged"));
      await expect(contract.anchor(ID, forged, inputHash, sourceHash, CID, 9900)).to.be
        .reverted;

      const record = await contract.getRecord(ID);
      expect(record.evidenceHash).to.equal(evidenceHash);
      expect(record.similarityBp).to.equal(SIMILARITY_BP);
    });
  });

  describe("validation", function () {
    it("rejects an empty verification id", async function () {
      await expect(
        contract.anchor("", evidenceHash, inputHash, sourceHash, CID, SIMILARITY_BP)
      ).to.be.revertedWithCustomError(contract, "EmptyVerificationId");
    });

    it("rejects a zero evidence hash", async function () {
      // Zero is the sentinel for "no record", so storing it would make an
      // anchored record indistinguishable from an absent one.
      await expect(
        contract.anchor(ID, ZERO, inputHash, sourceHash, CID, SIMILARITY_BP)
      ).to.be.revertedWithCustomError(contract, "EmptyEvidenceHash");
    });

    it("reverts when reading an unknown record", async function () {
      await expect(contract.getRecord("VER-DOES-NOT-EXIST")).to.be.revertedWithCustomError(
        contract,
        "UnknownRecord"
      );
    });
  });

  describe("integrity checking", function () {
    beforeEach(async function () {
      await contract.anchor(ID, evidenceHash, inputHash, sourceHash, CID, SIMILARITY_BP);
    });

    it("confirms a matching evidence hash", async function () {
      const [matches, stored] = await contract.verifyEvidence(ID, evidenceHash);
      expect(matches).to.equal(true);
      expect(stored).to.equal(evidenceHash);
    });

    it("detects a tampered evidence hash", async function () {
      const tampered = ethers.keccak256(ethers.toUtf8Bytes("evidence-tampered"));
      const [matches, stored] = await contract.verifyEvidence(ID, tampered);
      expect(matches).to.equal(false);
      expect(stored).to.equal(evidenceHash);
    });

    it("reports no match for an unknown id rather than reverting", async function () {
      const [matches, stored] = await contract.verifyEvidence("VER-NOPE", evidenceHash);
      expect(matches).to.equal(false);
      expect(stored).to.equal(ZERO);
    });

    it("finds the run that anchored a given evidence hash", async function () {
      const idKey = await contract.idKeyForEvidence(evidenceHash);
      expect(idKey).to.equal(ethers.keccak256(ethers.toUtf8Bytes(ID)));

      const record = await contract.getRecordByKey(idKey);
      expect(record.cid).to.equal(CID);
    });

    it("reports whether an id is anchored", async function () {
      expect(await contract.isAnchored(ID)).to.equal(true);
      expect(await contract.isAnchored("VER-NOPE")).to.equal(false);
    });
  });

  describe("enumeration", function () {
    it("counts and indexes anchored records", async function () {
      expect(await contract.totalRecords()).to.equal(0);

      await contract.anchor("VER-1", evidenceHash, inputHash, sourceHash, CID, 8300);
      await contract.anchor(
        "VER-2",
        ethers.keccak256(ethers.toUtf8Bytes("e2")),
        inputHash,
        sourceHash,
        CID,
        4100
      );

      expect(await contract.totalRecords()).to.equal(2);
      expect(await contract.idKeyAt(0)).to.equal(
        ethers.keccak256(ethers.toUtf8Bytes("VER-1"))
      );
    });
  });

  describe("gas", function () {
    it("anchors within a predictable budget", async function () {
      const tx = await contract.anchor(
        ID,
        evidenceHash,
        inputHash,
        sourceHash,
        CID,
        SIMILARITY_BP
      );
      const receipt = await tx.wait();
      console.log(`      gas used: ${receipt.gasUsed.toString()}`);
      // Guards against an accidental change that makes anchoring expensive.
      expect(receipt.gasUsed).to.be.lessThan(300000n);
    });
  });
});
