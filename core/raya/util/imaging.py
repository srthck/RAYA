"""Image decoding and validation.

Decoding is deliberately strict and happens once, up front. An image that
cannot be decoded here never reaches the face models, and the bytes we hash
are always the exact bytes the user supplied -- not a re-encoded copy.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

from ..config import Settings
from ..errors import ImageTooLargeError, InvalidImageError, UnsupportedFormatError

# Pillow refuses absurd images by default; we set our own explicit ceiling and
# surface a typed error rather than letting the DecompressionBombError escape.
Image.MAX_IMAGE_PIXELS = None

SUPPORTED_FORMATS = {"JPEG", "PNG", "WEBP", "BMP", "TIFF"}
FORMAT_TO_MIME = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
    "BMP": "image/bmp",
    "TIFF": "image/tiff",
}


@dataclass
class DecodedImage:
    """A validated image plus the provenance of the bytes it came from."""

    bgr: np.ndarray
    width: int
    height: int
    format: str
    mime: str
    byte_size: int

    def to_dict(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "format": self.format,
            "mime": self.mime,
            "byte_size": self.byte_size,
        }


def decode_image(data: bytes, settings: Settings) -> DecodedImage:
    """Validate and decode image bytes into an OpenCV BGR array."""
    if not data:
        raise InvalidImageError("Empty file.")
    if len(data) > settings.max_upload_bytes:
        raise ImageTooLargeError(
            f"Image is {len(data) / 1e6:.1f} MB; the limit is "
            f"{settings.max_upload_bytes / 1e6:.0f} MB.",
            byte_size=len(data),
        )

    try:
        probe = Image.open(io.BytesIO(data))
        fmt = (probe.format or "").upper()
        width, height = probe.size
    except UnidentifiedImageError:
        raise InvalidImageError("File is not a decodable image.")
    except Exception as exc:  # noqa: BLE001 - Pillow raises many decode errors
        raise InvalidImageError(f"Image could not be read: {exc}")

    if fmt not in SUPPORTED_FORMATS:
        raise UnsupportedFormatError(
            f"{fmt or 'Unknown'} is not a supported image format.", format=fmt
        )
    if width * height > settings.max_image_pixels:
        raise ImageTooLargeError(
            f"Image is {width}x{height}; the limit is "
            f"{settings.max_image_pixels:,} pixels.",
            width=width,
            height=height,
        )
    if min(width, height) < settings.min_image_dimension:
        raise InvalidImageError(
            f"Image is {width}x{height}; the shortest side must be at least "
            f"{settings.min_image_dimension} px.",
            width=width,
            height=height,
        )

    array = np.frombuffer(data, dtype=np.uint8)
    bgr = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if bgr is None:
        raise InvalidImageError("OpenCV could not decode this image.")

    # Honour EXIF orientation so a rotated phone photo is not handed to the
    # detector sideways, which measurably costs recall.
    bgr = _apply_exif_orientation(bgr, probe)

    return DecodedImage(
        bgr=bgr,
        width=bgr.shape[1],
        height=bgr.shape[0],
        format=fmt,
        mime=FORMAT_TO_MIME.get(fmt, "application/octet-stream"),
        byte_size=len(data),
    )


_EXIF_ORIENTATION_TAG = 274
_ORIENTATION_OPS = {
    2: lambda i: cv2.flip(i, 1),
    3: lambda i: cv2.rotate(i, cv2.ROTATE_180),
    4: lambda i: cv2.flip(i, 0),
    5: lambda i: cv2.flip(cv2.rotate(i, cv2.ROTATE_90_CLOCKWISE), 1),
    6: lambda i: cv2.rotate(i, cv2.ROTATE_90_CLOCKWISE),
    7: lambda i: cv2.flip(cv2.rotate(i, cv2.ROTATE_90_COUNTERCLOCKWISE), 1),
    8: lambda i: cv2.rotate(i, cv2.ROTATE_90_COUNTERCLOCKWISE),
}


def _apply_exif_orientation(bgr: np.ndarray, probe: Image.Image) -> np.ndarray:
    try:
        exif = probe.getexif()
    except Exception:  # noqa: BLE001 - absent or malformed EXIF is not fatal
        return bgr
    if not exif:
        return bgr
    op = _ORIENTATION_OPS.get(exif.get(_EXIF_ORIENTATION_TAG))
    return op(bgr) if op else bgr


def encode_png(bgr: np.ndarray) -> bytes:
    """Encode a BGR array to PNG bytes (used for face thumbnails in the UI)."""
    ok, buf = cv2.imencode(".png", bgr)
    if not ok:
        raise InvalidImageError("Failed to encode image.")
    return buf.tobytes()


def encode_jpeg(bgr: np.ndarray, quality: int = 88) -> bytes:
    ok, buf = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
    if not ok:
        raise InvalidImageError("Failed to encode image.")
    return buf.tobytes()
