from .platforms import Platform, classify_url, PLATFORMS
from .types import Candidate, CandidateVerdict, CandidateStatus
from .retriever import CandidateRetriever, RetrievedImage
from .verifier import CandidateVerifier

__all__ = [
    "Platform",
    "classify_url",
    "PLATFORMS",
    "Candidate",
    "CandidateVerdict",
    "CandidateStatus",
    "CandidateRetriever",
    "RetrievedImage",
    "CandidateVerifier",
]
