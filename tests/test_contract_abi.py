"""The Python ABI must match the compiled contract.

`core/raya/chain/abi.py` is written by hand so the API can talk to an already
deployed contract without the Node toolchain present. That convenience is only
safe if the two cannot drift: a signature mismatch would surface at runtime as a
failed anchor, in the one stage the whole project rests on.

Skipped when the Hardhat artifact is absent (`cd blockchain && npx hardhat compile`).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from raya.chain.abi import RAYA_ANCHOR_ABI

ARTIFACT = (
    Path(__file__).resolve().parents[1]
    / "blockchain"
    / "artifacts"
    / "contracts"
    / "RayaEvidenceAnchor.sol"
    / "RayaEvidenceAnchor.json"
)


def _signature(entry: dict) -> str:
    """Render a canonical `name(type,type)` signature, flattening tuples."""

    def render(item: dict) -> str:
        if item["type"].startswith("tuple"):
            inner = ",".join(render(c) for c in item.get("components", []))
            return f"({inner}){item['type'][5:]}"
        return item["type"]

    args = ",".join(render(i) for i in entry.get("inputs", []))
    return f"{entry.get('name', '')}({args})"


@pytest.fixture(scope="module")
def compiled():
    if not ARTIFACT.exists():
        pytest.skip("contract not compiled; run `npx hardhat compile` in blockchain/")
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))["abi"]


def _by_kind(abi, kind):
    return {_signature(e): e for e in abi if e.get("type") == kind}


class TestAbiParity:
    @pytest.mark.parametrize("kind", ["function", "event", "error"])
    def test_every_python_entry_exists_in_the_contract(self, compiled, kind):
        ours = _by_kind(RAYA_ANCHOR_ABI, kind)
        theirs = _by_kind(compiled, kind)
        missing = set(ours) - set(theirs)
        assert not missing, f"{kind}s in abi.py that the contract does not have: {missing}"

    def test_no_contract_function_is_missing_from_python(self, compiled):
        """The Python side may omit nothing: every callable must be reachable."""
        ours = _by_kind(RAYA_ANCHOR_ABI, "function")
        theirs = _by_kind(compiled, "function")
        missing = set(theirs) - set(ours)
        assert not missing, f"contract functions absent from abi.py: {missing}"

    def test_output_types_agree(self, compiled):
        ours = _by_kind(RAYA_ANCHOR_ABI, "function")
        theirs = _by_kind(compiled, "function")
        for signature, entry in ours.items():
            expected = [_render(o) for o in theirs[signature].get("outputs", [])]
            actual = [_render(o) for o in entry.get("outputs", [])]
            assert actual == expected, f"{signature} outputs differ: {actual} != {expected}"

    def test_state_mutability_agrees(self, compiled):
        """A view function marked nonpayable (or vice versa) would send a
        transaction where a call was intended, and cost gas to read."""
        ours = _by_kind(RAYA_ANCHOR_ABI, "function")
        theirs = _by_kind(compiled, "function")
        for signature, entry in ours.items():
            assert entry.get("stateMutability") == theirs[signature].get("stateMutability"), (
                f"{signature} mutability differs"
            )

    def test_event_indexing_agrees(self, compiled):
        """Indexed-ness changes topic layout, so a mismatch breaks log filters."""
        ours = _by_kind(RAYA_ANCHOR_ABI, "event")
        theirs = _by_kind(compiled, "event")
        for signature, entry in ours.items():
            mine = [(i["name"], i.get("indexed", False)) for i in entry["inputs"]]
            other = [(i["name"], i.get("indexed", False)) for i in theirs[signature]["inputs"]]
            assert mine == other, f"{signature} indexed flags differ"

    def test_the_record_struct_matches(self, compiled):
        """Field order defines tuple decoding: a reordering silently swaps
        `inputHash` and `sourceHash` in every read-back."""
        ours = next(e for e in RAYA_ANCHOR_ABI if e.get("name") == "getRecord")
        theirs = next(
            e for e in compiled if e.get("name") == "getRecord" and e.get("type") == "function"
        )
        mine = [(c["name"], c["type"]) for c in ours["outputs"][0]["components"]]
        other = [(c["name"], c["type"]) for c in theirs["outputs"][0]["components"]]
        assert mine == other


def _render(item: dict) -> str:
    if item["type"].startswith("tuple"):
        inner = ",".join(_render(c) for c in item.get("components", []))
        return f"({inner}){item['type'][5:]}"
    return item["type"]


class TestSimilarityEncoding:
    """Basis-point conversion must round-trip: this is how a float score
    survives a chain that has no floats."""

    @pytest.mark.parametrize("value", [0.0, 0.363, 0.4, 0.8140, 1.0, -0.15, -1.0])
    def test_round_trips_within_precision(self, value):
        from raya.chain.anchor import bp_to_similarity, similarity_to_bp

        assert bp_to_similarity(similarity_to_bp(value)) == pytest.approx(value, abs=5e-5)

    def test_stays_within_int32(self, compiled):
        from raya.chain.anchor import similarity_to_bp

        for value in (-1.0, 1.0):
            assert -(2**31) <= similarity_to_bp(value) <= 2**31 - 1

    def test_a_negative_score_is_not_clamped(self):
        from raya.chain.anchor import similarity_to_bp

        assert similarity_to_bp(-0.15) == -1500
