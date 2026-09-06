require("@nomicfoundation/hardhat-toolbox");
require("dotenv").config({ path: "../.env" });

const PRIVATE_KEY = process.env.DEPLOYER_PRIVATE_KEY || "";

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
