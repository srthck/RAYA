"""Canonicalization, hashing, integrity and the tamper demonstration.

These tests defend the property the blockchain layer exists to provide: the
same logical record always produces the same digest, and any change to the
record produces a different one.
"""

from __future__ import annotations

import json

import pytest

from raya.evidence.bundle import EvidenceBundle
from raya.evidence.integrity import check_integrity, simulate_tamper
from raya.storage.ipfs import cidv1_raw
from raya.util.canonical import canonical_bytes, canonical_json
from raya.util.hashing import sha256_bytes, sha256_canonical


class TestCanonicalJson:
    def test_key_order_does_not_change_the_output(self):
        a = {"b": 1, "a": 2, "c": {"z": 1, "y": 2}}
        b = {"c": {"y": 2, "z": 1}, "a": 2, "b": 1}
        assert canonical_json(a) == canonical_json(b)
        assert sha256_canonical(a) == sha256_canonical(b)

    def test_output_has_no_insignificant_whitespace(self):
        assert canonical_json({"a": 1, "b": [1, 2]}) == '{"a":1,"b":[1,2]}'

    def test_non_ascii_is_emitted_literally(self):
        assert canonical_json({"name": "Zoë"}) == '{"name":"Zoë"}'

    def test_floats_are_rounded_to_a_fixed_precision(self):
        assert canonical_json({"s": 0.123456789}) == '{"s":0.123457}'

    def test_negative_zero_is_normalised(self):
        assert canonical_json({"s": -0.0}) == canonical_json({"s": 0.0})

    def test_nan_and_infinity_are_rejected(self):
        for value in (float("nan"), float("inf"), float("-inf")):
            with pytest.raises(ValueError):
                canonical_json({"s": value})

    def test_unserializable_types_are_rejected(self):
        with pytest.raises(TypeError):
            canonical_json({"when": object()})

    def test_output_is_valid_json(self):
        record = {"a": [1, {"b": "x"}], "c": None, "d": True}
        assert json.loads(canonical_json(record)) == record

    def test_round_trip_is_stable(self):
        """Re-parsing and re-canonicalizing must reproduce the same bytes."""
        record = {"z": 1, "a": {"n": 0.5, "s": "x"}, "l": [3, 2, 1]}
        once = canonical_bytes(record)
        twice = canonical_bytes(json.loads(once.decode("utf-8")))
        assert once == twice


class TestEvidenceBundle:
    @pytest.fixture
    def record(self):
        return {
            "schema_version": "1.0",
            "verification_id": "VER-TEST-0001",
            "match": {"similarity": 0.83, "platform": "x"},
            "input": {"sha256": "a" * 64},
        }

    def test_hash_matches_the_frozen_bytes(self, record):
        bundle = EvidenceBundle.create(record)
        assert bundle.sha256 == sha256_bytes(bundle.canonical)
        assert bundle.verify_self()

    def test_recompute_agrees_with_the_stored_hash(self, record):
        bundle = EvidenceBundle.create(record)
        assert bundle.recompute() == bundle.sha256

    def test_two_bundles_of_the_same_record_agree(self, record):
        assert EvidenceBundle.create(record).sha256 == EvidenceBundle.create(dict(record)).sha256

    def test_pretty_output_is_not_the_hashed_form(self, record):
        """The exported pretty file must not be mistaken for the canonical one."""
        bundle = EvidenceBundle.create(record)
        assert bundle.pretty().encode("utf-8") != bundle.canonical
        assert json.loads(bundle.pretty()) == record

    def test_a_changed_field_changes_the_hash(self, record):
        first = EvidenceBundle.create(record).sha256
        record["match"]["similarity"] = 0.84
        assert EvidenceBundle.create(record).sha256 != first


class TestIntegrity:
    @pytest.fixture
    def bundle(self):
        return EvidenceBundle.create({"schema_version": "1.0", "match": {"similarity": 0.83}})

    def test_matching_chain_hash_verifies(self, bundle):
        report = check_integrity(bundle, onchain_hash=bundle.sha256)
        assert report.verified
        assert report.anchored

    def test_accepts_an_0x_prefixed_chain_hash(self, bundle):
        report = check_integrity(bundle, onchain_hash="0x" + bundle.sha256)
        assert report.verified

    def test_mismatched_chain_hash_fails(self, bundle):
        report = check_integrity(bundle, onchain_hash="b" * 64)
        assert not report.verified
        assert not report.anchored

    def test_unanchored_run_is_not_reported_as_verified(self, bundle):
        """Absent an anchor, the only check that ran is self-consistency.

        That must not be dressed up as "integrity verified" in the anchored
        sense -- `anchored` stays False.
        """
        report = check_integrity(bundle, onchain_hash=None)
        assert not report.anchored
        chain_check = next(c for c in report.checks if c.name == "chain_match")
        assert chain_check.performed is False

    def test_ipfs_copy_is_compared(self, bundle):
        good = check_integrity(bundle, bundle.sha256, ipfs_bytes=bundle.canonical)
        assert good.verified

        bad = check_integrity(bundle, bundle.sha256, ipfs_bytes=b'{"tampered":true}')
        assert not bad.verified

    def test_summary_names_the_failing_check(self, bundle):
        report = check_integrity(bundle, onchain_hash="c" * 64)
        assert "failed" in report.summary().lower()

    def test_self_consistency_alone_is_not_called_verified(self, bundle):
        """Re-hashing our own bytes proves only that this process did not
        corrupt them. Saying "integrity verified" on that basis would be the
        exact overclaim the project exists to avoid."""
        report = check_integrity(bundle, onchain_hash=None, ipfs_bytes=None)
        summary = report.summary()

        assert not report.independently_checked
        assert "Integrity verified" not in summary
        assert "self-consistent" in summary
        assert "nothing independent was checked" in summary

    def test_summary_names_the_independent_source(self, bundle):
        chain_only = check_integrity(bundle, onchain_hash=bundle.sha256)
        assert chain_only.independently_checked
        assert "Integrity verified" in chain_only.summary()
        assert "on-chain anchor" in chain_only.summary()

        both = check_integrity(bundle, bundle.sha256, ipfs_bytes=bundle.canonical)
        assert "on-chain anchor" in both.summary()
        assert "IPFS" in both.summary()

    def test_ipfs_alone_counts_as_independent(self, bundle):
        report = check_integrity(bundle, onchain_hash=None, ipfs_bytes=bundle.canonical)
        assert report.independently_checked
        assert not report.anchored
        assert "IPFS" in report.summary()


class TestTamperDetection:
    @pytest.fixture
    def bundle(self):
        return EvidenceBundle.create(
            {
                "schema_version": "1.0",
                "match": {"similarity": 0.83, "post_url": "https://x.com/u/status/1"},
                "verification": {"threshold": 0.4},
            }
        )

    def test_altering_a_score_is_detected(self, bundle):
        result = simulate_tamper(bundle, "match.similarity")
        assert result.detected
        assert result.tampered_hash != result.original_hash

    def test_altering_a_url_is_detected(self, bundle):
        result = simulate_tamper(bundle, "match.post_url")
        assert result.detected

    def test_the_original_bundle_is_untouched(self, bundle):
        before = bundle.sha256
        simulate_tamper(bundle, "match.similarity")
        assert bundle.sha256 == before
        assert bundle.record["match"]["similarity"] == 0.83

    def test_compares_against_the_anchored_hash_when_given(self, bundle):
        result = simulate_tamper(bundle, "match.similarity", anchored_hash="0x" + bundle.sha256)
        assert result.detected
        assert result.anchored_hash == bundle.sha256

    def test_an_unknown_field_raises(self, bundle):
        with pytest.raises(KeyError):
            simulate_tamper(bundle, "match.nonexistent")

    def test_an_explicit_value_is_used(self, bundle):
        result = simulate_tamper(bundle, "match.similarity", new_value=0.99)
        assert result.tampered_value == 0.99
        assert result.detected


class TestCid:
    def test_matches_the_ipfs_reference_vector(self):
        """`ipfs add --cid-version=1 --raw-leaves` of "hello world"."""
        assert (
            cidv1_raw(b"hello world")
            == "bafkreifzjut3te2nhyekklss27nh3k72ysco7y32koao5eei66wof36n5e"
        )

    def test_is_content_addressed(self):
        assert cidv1_raw(b"a") != cidv1_raw(b"b")
        assert cidv1_raw(b"a") == cidv1_raw(b"a")

    def test_uses_the_raw_codec_prefix(self):
        assert cidv1_raw(b"anything").startswith("bafkrei")
