/**
 * Deploy RayaEvidenceAnchor.
 *
 * The script does three things beyond deploying: it refuses to run against an
 * unexpected chain id, it performs a live round-trip (anchor a record, read it
 * back, compare) before declaring success, and it writes the resulting address
 * to a deployments file the Python side can read.
 *
 * The round-trip matters. A deployment that succeeds but whose storage does not
 * read back correctly would fail later, mid-demo, in the one stage the whole
 * project rests on.
 */

const fs = require("fs");
const path = require("path");
const hre = require("hardhat");

const EXPECTED_CHAIN_ID = 11155111n;

async function main() {
  const network = await hre.ethers.provider.getNetwork();
  const [deployer] = await hre.ethers.getSigners();

  if (!deployer) {
    throw new Error(
      "No signer available. Set DEPLOYER_PRIVATE_KEY in .env before deploying."
    );
  }

  const balance = await hre.ethers.provider.getBalance(deployer.address);

  console.log("RAYA evidence anchor deployment");
  console.log("-".repeat(58));
  console.log(`Network      ${hre.network.name} (chain id ${network.chainId})`);
  console.log(`Deployer     ${deployer.address}`);
  console.log(`Balance      ${hre.ethers.formatEther(balance)}`);

  if (hre.network.name === "sepolia" && network.chainId !== EXPECTED_CHAIN_ID) {
    throw new Error(
      `Expected Ethereum Sepolia (chain id ${EXPECTED_CHAIN_ID}) but the RPC reports ` +
        `${network.chainId}. Refusing to deploy to the wrong network.`
    );
  }

  if (balance === 0n) {
    throw new Error(
      `${deployer.address} has no balance. Fund it at ` +
        "an Ethereum Sepolia faucet and try again."
    );
  }

  console.log("\nDeploying...");
  const factory = await hre.ethers.getContractFactory("RayaEvidenceAnchor");
  const contract = await factory.deploy();
  await contract.waitForDeployment();

  const address = await contract.getAddress();
  const deployTx = contract.deploymentTransaction();
  const receipt = await deployTx.wait();

  console.log(`Contract     ${address}`);
  console.log(`Tx           ${deployTx.hash}`);
  console.log(`Block        ${receipt.blockNumber}`);
  console.log(`Gas used     ${receipt.gasUsed.toString()}`);

  // Live round-trip before we call this a success.
  console.log("\nVerifying storage with a round-trip...");
  const probeId = `VER-DEPLOY-${Date.now()}`;
  const evidenceHash = hre.ethers.keccak256(hre.ethers.toUtf8Bytes(probeId));
  const zero = "0x" + "0".repeat(64);

  const tx = await contract.anchor(probeId, evidenceHash, zero, zero, "deployment-probe", 8300);
  await tx.wait();

  const stored = await contract.getRecord(probeId);
  if (stored.evidenceHash !== evidenceHash) {
    throw new Error("Read-back mismatch: the contract did not store what was written.");
  }
  const [matches] = await contract.verifyEvidence(probeId, evidenceHash);
  if (!matches) {
    throw new Error("verifyEvidence returned false for a record just written.");
  }
  console.log("Round-trip    OK (write, read back, compare)");

  const deployment = {
    network: hre.network.name,
    chainId: Number(network.chainId),
    contractAddress: address,
    deploymentTx: deployTx.hash,
    blockNumber: receipt.blockNumber,
    deployer: deployer.address,
    deployedAt: new Date().toISOString(),
    explorer: `https://sepolia.etherscan.io/address/${address}`,
  };

  const outDir = path.join(__dirname, "..", "deployments");
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(
    path.join(outDir, `${hre.network.name}.json`),
    JSON.stringify(deployment, null, 2)
  );

  console.log("\n" + "=".repeat(58));
  console.log("Add this to your .env:\n");
  console.log(`CONTRACT_ADDRESS=${address}`);
  console.log("\nExplorer:");
  console.log(`  ${deployment.explorer}`);
  console.log("=".repeat(58));
}

main().catch((error) => {
  console.error("\nDeployment failed:", error.message);
  process.exitCode = 1;
});
