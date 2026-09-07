"""Anchoring evidence on Ethereum Sepolia, and reading it back.

The read-back is the point. Submitting a transaction proves nothing on its own:
it can revert, it can be dropped, it can land with different data than intended.
RAYA therefore waits for the receipt, checks `status == 1`, then makes a fresh
`eth_call` to the contract and compares the stored hash against the local one.
Only that comparison is allowed to produce the words "integrity verified".

If any step fails, the run keeps its verified face match and reports the anchor
as failed. A face match and a blockchain anchor are separate claims, and RAYA
never lets a failure in the second quietly weaken or strengthen the first.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from ..config import Settings, get_settings
from ..errors import AnchorError, ChainNotConfiguredError
from .abi import RAYA_ANCHOR_ABI


def similarity_to_bp(similarity: float) -> int:
    """Convert a cosine score to basis points for on-chain storage.

    Solidity has no floats. Basis points keep four decimal places, which is
    more resolution than the comparison itself meaningfully carries, and the
    conversion is exact and reversible.
    """
    return int(round(similarity * 10_000))


def bp_to_similarity(basis_points: int) -> float:
    return round(basis_points / 10_000, 6)


@dataclass
class AnchorReceipt:
    tx_hash: str
    block_number: int
    block_hash: str
    gas_used: int
    effective_gas_price: Optional[int]
    chain_id: int
    chain_name: str
    contract_address: str
    submitter: str
    explorer_tx_url: str
    explorer_address_url: str
    confirmed_at: float
    duration_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "tx_hash": self.tx_hash,
            "block_number": self.block_number,
            "block_hash": self.block_hash,
            "gas_used": self.gas_used,
            "effective_gas_price": self.effective_gas_price,
            "chain_id": self.chain_id,
            "chain_name": self.chain_name,
            "contract_address": self.contract_address,
            "submitter": self.submitter,
            "explorer_tx_url": self.explorer_tx_url,
            "explorer_address_url": self.explorer_address_url,
            "confirmed_at": self.confirmed_at,
            "duration_ms": self.duration_ms,
        }


@dataclass
class OnChainRecord:
    evidence_hash: str
    input_hash: str
    source_hash: str
    cid: str
    similarity: float
    anchored_at: int
    submitter: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_hash": self.evidence_hash,
            "input_hash": self.input_hash,
            "source_hash": self.source_hash,
            "cid": self.cid,
            "similarity": self.similarity,
            "anchored_at": self.anchored_at,
            "submitter": self.submitter,
        }


class BlockchainAnchor(ABC):
    name: str

    @abstractmethod
    def anchor(
        self,
        verification_id: str,
        evidence_hash: str,
        input_hash: str,
        source_hash: str,
        cid: str,
        similarity: float,
    ) -> AnchorReceipt: ...

    @abstractmethod
    def read_record(self, verification_id: str) -> OnChainRecord: ...

    @property
    @abstractmethod
    def configured(self) -> bool: ...


class EvmAnchor(BlockchainAnchor):
    """Anchor on an EVM chain (Ethereum Sepolia, chain id 11155111) via web3.py."""

    name = "sepolia"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._w3 = None
        self._contract = None
        self._account = None

    # ---- connection --------------------------------------------------------

    @property
    def configured(self) -> bool:
        return bool(self.settings.contract_address and self.settings.deployer_private_key)

    def _connect(self):
        if self._w3 is not None:
            return
        if not self.configured:
            raise ChainNotConfiguredError(
                "CONTRACT_ADDRESS and DEPLOYER_PRIVATE_KEY must be set to anchor "
                "evidence. Deploy the contract with `npm run deploy` in blockchain/."
            )

        from web3 import Web3
        from web3.middleware import ExtraDataToPOAMiddleware

        w3 = Web3(Web3.HTTPProvider(self.settings.chain_rpc_url, request_kwargs={"timeout": 30}))

        # Some EVM testnets produce blocks with an extraData field longer than
        # the 32 bytes the default formatter accepts, so the POA middleware is
        # injected defensively: it is harmless on Sepolia and required elsewhere.
        try:
            w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
        except Exception:  # noqa: BLE001 - older web3 exposes a different name
            try:
                from web3.middleware import geth_poa_middleware

                w3.middleware_onion.inject(geth_poa_middleware, layer=0)
            except Exception:
                pass

        if not w3.is_connected():
            raise AnchorError(f"Could not connect to {self.settings.chain_rpc_url}.")

        actual_chain_id = w3.eth.chain_id
        if actual_chain_id != self.settings.chain_id:
            raise AnchorError(
                f"RPC reports chain id {actual_chain_id}, but CHAIN_ID is configured "
                f"as {self.settings.chain_id}. Refusing to anchor to the wrong network."
            )

        self._account = w3.eth.account.from_key(self.settings.deployer_private_key)
        self._contract = w3.eth.contract(
            address=Web3.to_checksum_address(self.settings.contract_address),
            abi=RAYA_ANCHOR_ABI,
        )
        self._w3 = w3

    # ---- writing -----------------------------------------------------------

    def anchor(
        self,
        verification_id: str,
        evidence_hash: str,
        input_hash: str,
        source_hash: str,
        cid: str,
        similarity: float,
    ) -> AnchorReceipt:
        self._connect()
        w3, contract, account = self._w3, self._contract, self._account
        started = time.perf_counter()

        args = (
            verification_id,
            _to_bytes32(evidence_hash),
            _to_bytes32(input_hash),
            _to_bytes32(source_hash or "0" * 64),
            cid or "",
            similarity_to_bp(similarity),
        )

        function = contract.functions.anchor(*args)

        # Simulate first. A revert caught here (already anchored, bad input)
        # costs nothing, whereas discovering it from a failed receipt costs gas
        # and gives a far worse error message.
        try:
            function.call({"from": account.address})
        except Exception as exc:  # noqa: BLE001 - surface the revert reason as-is
            raise AnchorError(f"Anchor transaction would revert: {_reason(exc)}")

        try:
            gas_estimate = function.estimate_gas({"from": account.address})
        except Exception:  # noqa: BLE001 - fall back to a safe ceiling
            gas_estimate = 500_000

        balance = w3.eth.get_balance(account.address)
        gas_price = w3.eth.gas_price
        if balance < gas_estimate * gas_price:
            raise AnchorError(
                f"Account {account.address} has insufficient "
                f"{self.settings.chain_currency} for gas. Fund it from a "
                f"{self.settings.chain_name} faucet.",
                address=account.address,
                balance=str(balance),
            )

        tx = function.build_transaction(
            {
                "from": account.address,
                "nonce": w3.eth.get_transaction_count(account.address),
                "gas": int(gas_estimate * 1.25),
                "gasPrice": gas_price,
                "chainId": self.settings.chain_id,
            }
        )
        signed = account.sign_transaction(tx)
        raw = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")

        try:
            tx_hash = w3.eth.send_raw_transaction(raw)
        except Exception as exc:  # noqa: BLE001
            raise AnchorError(f"Could not broadcast the anchor transaction: {exc}")

        try:
            receipt = w3.eth.wait_for_transaction_receipt(
                tx_hash, timeout=self.settings.chain_tx_timeout_s
            )
        except Exception:  # noqa: BLE001
            raise AnchorError(
                f"Transaction {tx_hash.hex()} was broadcast but did not confirm within "
                f"{self.settings.chain_tx_timeout_s:.0f}s. It may still land later.",
                tx_hash=_hex(tx_hash),
            )

        if receipt.status != 1:
            raise AnchorError(
                f"Anchor transaction {_hex(tx_hash)} reverted on chain.",
                tx_hash=_hex(tx_hash),
            )

        tx_hex = _hex(tx_hash)
        return AnchorReceipt(
            tx_hash=tx_hex,
            block_number=receipt.blockNumber,
            block_hash=_hex(receipt.blockHash),
            gas_used=receipt.gasUsed,
            effective_gas_price=getattr(receipt, "effectiveGasPrice", None),
            chain_id=self.settings.chain_id,
            chain_name=self.settings.chain_name,
            contract_address=self.settings.contract_address,
            submitter=account.address,
            explorer_tx_url=f"{self.settings.chain_explorer.rstrip('/')}/tx/{tx_hex}",
            explorer_address_url=(
                f"{self.settings.chain_explorer.rstrip('/')}/address/"
                f"{self.settings.contract_address}"
            ),
            confirmed_at=time.time(),
            duration_ms=int((time.perf_counter() - started) * 1000),
        )

    # ---- reading back ------------------------------------------------------

    def read_record(self, verification_id: str) -> OnChainRecord:
        """Fetch the stored record with a fresh call.

        Deliberately not read from the transaction receipt or its logs: those
        are what we submitted. Querying contract state is what proves the chain
        actually holds the value.
        """
        self._connect()
        try:
            raw = self._contract.functions.getRecord(verification_id).call()
        except Exception as exc:  # noqa: BLE001
            raise AnchorError(f"Could not read the record back: {_reason(exc)}")

        return OnChainRecord(
            evidence_hash=_hex(raw[0]),
            input_hash=_hex(raw[1]),
            source_hash=_hex(raw[2]),
            cid=raw[3],
            similarity=bp_to_similarity(raw[4]),
            anchored_at=raw[5],
            submitter=raw[6],
        )

    def verify_onchain(self, verification_id: str, expected_hash: str) -> tuple[bool, str]:
        """Ask the contract itself whether the anchored hash matches."""
        self._connect()
        matches, stored = self._contract.functions.verifyEvidence(
            verification_id, _to_bytes32(expected_hash)
        ).call()
        return bool(matches), _hex(stored)

    def describe(self) -> dict[str, Any]:
        return {
            "provider": self.name,
            "chain_name": self.settings.chain_name,
            "chain_id": self.settings.chain_id,
            "rpc_url": self.settings.chain_rpc_url,
            "explorer": self.settings.chain_explorer,
            "contract_address": self.settings.contract_address,
            "configured": self.configured,
        }


# ---- helpers ---------------------------------------------------------------


def _to_bytes32(value: str) -> bytes:
    """Accept a hex digest with or without 0x and return exactly 32 bytes."""
    cleaned = value[2:] if value.startswith("0x") else value
    data = bytes.fromhex(cleaned)
    if len(data) != 32:
        raise AnchorError(f"Expected a 32-byte hash, got {len(data)} bytes.")
    return data


def _hex(value) -> str:
    if isinstance(value, (bytes, bytearray)):
        return "0x" + value.hex()
    if hasattr(value, "hex"):
        result = value.hex()
        return result if result.startswith("0x") else "0x" + result
    return str(value)


def _reason(exc: Exception) -> str:
    """Pull a human-readable revert reason out of a web3 exception."""
    message = str(exc)
    for name in ("AlreadyAnchored", "UnknownRecord", "EmptyEvidenceHash", "EmptyVerificationId"):
        if name in message:
            return {
                "AlreadyAnchored": "this verification id is already anchored (records are write-once)",
                "UnknownRecord": "no record exists for this verification id",
                "EmptyEvidenceHash": "the evidence hash was empty",
                "EmptyVerificationId": "the verification id was empty",
            }[name]
    return message[:300]


def build_anchor(settings: Settings | None = None) -> EvmAnchor:
    return EvmAnchor(settings or get_settings())
