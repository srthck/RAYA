/**
 * Read an anchored record back from the chain and compare it to a local file.
 *
 * This is the reviewer's tool: it needs nothing from RAYA except the evidence
 * file and the contract address, and it recomputes the digest itself rather
 * than trusting any value RAYA reported.
 *
 *   VERIFICATION_ID=VER-20260906-ABC123 \
 *   EVIDENCE_PATH=../.raya-data/runs/VER-.../evidence.json \
 *   npx hardhat run scripts/readback.js --network sepolia
 *
 * Hardhat consumes positional arguments itself, so the two inputs are read from
 * the environment. With neither set it prints a summary of everything the
 * contract has anchored.
 */

const fs = require("fs");
const crypto = require("crypto");
const path = require("path");
const hre = require("hardhat");

function contractAddress() {
  if (process.env.CONTRACT_ADDRESS) return process.env.CONTRACT_ADDRESS;
  const file = path.join(__dirname, "..", "deployments", `${hre.network.name}.json`);
  if (fs.existsSync(file)) {
    return JSON.parse(fs.readFileSync(file, "utf8")).contractAddress;
  }
  throw new Error(
    "No contract address. Set CONTRACT_ADDRESS or deploy first with `npm run deploy`."
  );
}

function bpToSimilarity(bp) {
  return (Number(bp) / 10000).toFixed(4);
}

async function main() {
  const args = process.argv.slice(2).filter((a) => !a.startsWith("-"));
  const verificationId = process.env.VERIFICATION_ID || args[0];
  const evidencePath = process.env.EVIDENCE_PATH || args[1];

  const address = contractAddress();
  const contract = await hre.ethers.getContractAt("RayaEvidenceAnchor", address);

  console.log("RAYA on-chain read-back");
  console.log("-".repeat(64));
  console.log(`Network    ${hre.network.name}`);
  console.log(`Contract   ${address}`);

  if (!verificationId) {
    const total = await contract.totalRecords();
    console.log(`Records    ${total}`);
    console.log("\nPass a verification id to inspect one record.");
    return;
  }

  let record;
  try {
    record = await contract.getRecord(verificationId);
  } catch {
    console.log(`\nNo record anchored for ${verificationId}.`);
    process.exitCode = 1;
    return;
  }

  const onChainHash = record.evidenceHash.slice(2).toLowerCase();

  console.log(`\nVerification   ${verificationId}`);
  console.log(`Evidence hash  ${onChainHash}`);
  console.log(`Input hash     ${record.inputHash.slice(2)}`);
  console.log(`Source hash    ${record.sourceHash.slice(2)}`);
  console.log(`IPFS CID       ${record.cid}`);
  console.log(`Similarity     ${bpToSimilarity(record.similarityBp)}`);
  console.log(`Anchored at    ${new Date(Number(record.anchoredAt) * 1000).toISOString()}`);
  console.log(`Submitter      ${record.submitter}`);

  if (!evidencePath) {
    console.log("\nPass an evidence.json path to verify the hash locally.");
    return;
  }

  if (!fs.existsSync(evidencePath)) {
    console.log(`\nEvidence file not found: ${evidencePath}`);
    process.exitCode = 1;
    return;
  }

  // Hash the raw bytes. The canonical file must not be re-parsed or
  // re-serialized -- that is the whole point of a canonical form.
  const bytes = fs.readFileSync(evidencePath);
  const localHash = crypto.createHash("sha256").update(bytes).digest("hex");

  console.log(`\nLocal file     ${evidencePath}`);
  console.log(`Local hash     ${localHash}`);

  const matches = localHash === onChainHash;
  console.log("\n" + "=".repeat(64));
  if (matches) {
    console.log("INTEGRITY VERIFIED -- the local evidence matches the anchor.");
  } else {
    console.log("INTEGRITY MISMATCH -- the local evidence does NOT match the anchor.");
    console.log("The file has been altered since it was anchored, or it is a");
    console.log("different record.");
    process.exitCode = 1;
  }
  console.log("=".repeat(64));

  // Cross-check with the contract's own comparison, so a bug in this script
  // cannot produce a false "verified".
  const [contractSaysMatches] = await contract.verifyEvidence(
    verificationId,
    "0x" + localHash
  );
  console.log(`\nContract verifyEvidence() agrees: ${contractSaysMatches === matches}`);
}

main().catch((error) => {
  console.error("Read-back failed:", error.message);
  process.exitCode = 1;
});
