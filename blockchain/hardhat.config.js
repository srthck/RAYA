require("@nomicfoundation/hardhat-toolbox");
require("dotenv").config({ path: "../.env" });

const RAW_KEY = process.env.DEPLOYER_PRIVATE_KEY || "";

/**
 * A deploy key is only accepted if it is actually shaped like one: 32 bytes of
 * hex, optionally 0x-prefixed.
 *
 * Hardhat validates `accounts` when it loads the config, for every task and
 * every network -- so a malformed value here (a wallet *address* pasted in
 * place of a private key is the common mistake) makes `hardhat test` fail
 * before a single local test runs, with an error that points at the network
 * config rather than at the cause. Filtering it out keeps the local suite
 * runnable and turns the failure into an explicit message at deploy time,
 * where it belongs.
 */
function usableDeployKey(value) {
  const hex = value.trim().replace(/^0x/i, "");
  if (hex.length === 0) return null;
  if (!/^[0-9a-fA-F]{64}$/.test(hex)) {
    // 40 hex chars is an address, not a key -- the mistake worth naming.
    const hint =
      hex.length === 40
        ? "that looks like a wallet address, not a private key"
        : `expected 64 hex characters, got ${hex.length}`;
    console.warn(
      `[raya] Ignoring DEPLOYER_PRIVATE_KEY: ${hint}. ` +
        "Local tasks will run; deployment to sepolia will refuse with no account.",
    );
    return null;
  }
  return `0x${hex}`;
}

const PRIVATE_KEY = usableDeployKey(RAW_KEY);

/**
 * Hardhat configuration for the RAYA evidence anchor.
 *
 * Ethereum Sepolia is the deployment target: a standard EVM chain (id
 * 11155111) needing only an RPC endpoint and a funded test key. Sepolia was
 * chosen over Ethereum Sepolia because Core's faucet CAPTCHA is broken
 * ("Invalid domain for site key"), which made funding impossible.
 */
module.exports = {
  solidity: {
    version: "0.8.24",
    settings: {
      optimizer: { enabled: true, runs: 200 },
      // The contract stores hashes and emits one event; there is nothing to
      // gain from via-IR here, and leaving it off keeps builds fast and the
      // deployed bytecode straightforward to reason about.
      evmVersion: "paris",
    },
  },
  networks: {
    hardhat: {
      chainId: 31337,
    },
    sepolia: {
      url: process.env.CHAIN_RPC_URL || "https://ethereum-sepolia-rpc.publicnode.com",
      chainId: 11155111,
      accounts: PRIVATE_KEY ? [PRIVATE_KEY] : [],
      // Sepolia gas is volatile; let the RPC estimate rather than pinning a
      // price that could leave the transaction stuck.
    },
  },
  etherscan: {
    apiKey: {
      sepolia: process.env.ETHERSCAN_API_KEY || "",
    },
  },
  paths: {
    sources: "./contracts",
    tests: "./test",
    cache: "./cache",
    artifacts: "./artifacts",
  },
};
