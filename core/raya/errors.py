"""Typed failure modes for the RAYA pipeline.

Every one of these maps to a specific, honest UI state. The pipeline never
converts a failure into a fabricated success: if a stage cannot complete, the
verification carries that fact all the way through to the evidence record.
"""

from __future__ import annotations


class RayaError(Exception):
    """Base class. `code` is the stable identifier the frontend switches on."""

    code = "raya_error"
    http_status = 400

    def __init__(self, message: str, **context):
        super().__init__(message)
        self.message = message
        self.context = context

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message, **self.context}


# ---- Stage 01: input -------------------------------------------------------

class InvalidImageError(RayaError):
    code = "invalid_image"


class ImageTooLargeError(RayaError):
    code = "image_too_large"


class UnsupportedFormatError(RayaError):
    code = "unsupported_format"


# ---- Stage 02/03: face -----------------------------------------------------

class NoFaceDetectedError(RayaError):
    code = "no_face_detected"


class MultipleFacesError(RayaError):
    """Raised when the caller did not disambiguate which face is the subject.

    Carries the candidate faces so the UI can render a selector rather than
    silently guessing.
    """

    code = "multiple_faces"

    def __init__(self, message: str, faces: list | None = None):
        super().__init__(message, faces=faces or [])


class FaceTooSmallError(RayaError):
    code = "face_too_small"


# ---- Stage 04/05: search ---------------------------------------------------

class SearchProviderError(RayaError):
    code = "search_provider_error"
    http_status = 502


class SearchProviderNotConfiguredError(RayaError):
    code = "search_provider_not_configured"
    http_status = 503


class NoCandidatesError(RayaError):
    code = "no_candidates"


class SourceUnreachableError(RayaError):
    """A candidate was discovered but its image could not be independently
    retrieved. This is a per-candidate condition, not a fatal one."""

    code = "source_unreachable"


# ---- Stage 07/08/09: evidence, storage, chain ------------------------------

class StorageError(RayaError):
    code = "storage_error"
    http_status = 502


class AnchorError(RayaError):
    code = "anchor_error"
    http_status = 502


class IntegrityMismatchError(RayaError):
    code = "integrity_mismatch"


class ChainNotConfiguredError(RayaError):
    code = "chain_not_configured"
    http_status = 503
