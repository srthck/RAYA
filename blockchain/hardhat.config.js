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
        "Local tasks will run; deployment to coreTestnet2 will refuse with no account.",
    );
    return null;
  }
  return `0x${hex}`;
}

const PRIVATE_KEY = usableDeployKey(RAW_KEY);

/**
 * Hardhat configuration for the RAYA evidence anchor.
 *
 * Core Testnet2 is an EVM chain (id 1114), so no custom tooling is required --
 * only the RPC endpoint and a funded test key. Contract verification points at
 * Core's Blockscout-compatible explorer API.
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
    coreTestnet2: {
      url: process.env.CHAIN_RPC_URL || "https://rpc.test2.btcs.network",
      chainId: 1114,
      accounts: PRIVATE_KEY ? [PRIVATE_KEY] : [],
      // Core's gas price is stable and low; an explicit value avoids the
      // occasional under-priced transaction when the RPC estimate lags.
      gasPrice: 30000000000,
    },
  },
  etherscan: {
    apiKey: {
      coreTestnet2: process.env.CORE_SCAN_API_KEY || "no-key-needed",
    },
    customChains: [
      {
        network: "coreTestnet2",
        chainId: 1114,
        urls: {
          apiURL: "https://scan.test2.btcs.network/api",
          browserURL: "https://scan.test2.btcs.network",
        },
      },
    ],
  },
  paths: {
    sources: "./contracts",
    tests: "./test",
    cache: "./cache",
    artifacts: "./artifacts",
  },
};
