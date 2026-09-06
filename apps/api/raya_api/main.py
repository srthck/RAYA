"""RAYA HTTP API.

The frontend is a view onto this API and nothing else -- every number it renders
comes from a response or an SSE event here. There is no client-side simulation
of progress, which is why the event stream is a first-class endpoint rather than
an afterthought.

Route groups:

    /v1/config                      what is configured, honestly
    /v1/uploads                     upload + detect, before any search
    /v1/verifications               start a run, read results
    /v1/verifications/{id}/events   live SSE, replayable from the stored log
    /v1/verifications/{id}/...      evidence, assets, export, integrity, tamper
"""

from __future__ import annotations

import asyncio
import io
import json
import time
import zipfile
from typing import Any, Optional

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from raya import __version__
from raya.config import get_settings
from raya.errors import RayaError
from raya.evidence.bundle import EvidenceBundle
from raya.evidence.integrity import check_integrity, simulate_tamper
from raya.util.hashing import sha256_bytes

from .runtime import Runtime, get_runtime

app = FastAPI(
    title="RAYA",
    version=__version__,
    description="Find the source. Verify the face. Anchor the evidence.",
    docs_url="/docs",
)

# The API and the Next.js dev server run on different ports, so the browser
# treats every call as cross-origin.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.exception_handler(RayaError)
async def raya_error_handler(request: Request, exc: RayaError) -> JSONResponse:
    """Typed pipeline errors become structured responses the UI can switch on."""
    return JSONResponse(status_code=exc.http_status, content={"error": exc.to_dict()})


# ---- models ----------------------------------------------------------------


class StartVerificationRequest(BaseModel):
    upload_id: str = Field(..., description="Id returned by POST /v1/uploads")
    face_index: Optional[int] = Field(
        None, description="Which detected face is the subject; required if several."
    )


class TamperRequest(BaseModel):
    field_path: str = Field(
        "match.similarity", description="Dotted path of the evidence field to alter"
    )
    new_value: Optional[Any] = Field(None, description="Value to substitute")


# ---- config ----------------------------------------------------------------


@app.get("/v1/health")
async def health(runtime: Runtime = Depends(get_runtime)) -> dict[str, Any]:
    return {"status": "ok", "version": __version__, "time": time.time()}


@app.get("/v1/config")
async def config(runtime: Runtime = Depends(get_runtime)) -> dict[str, Any]:
    """What this deployment can actually do.

    The UI uses this to disable capabilities rather than fail at the last step,
    and to show the reviewer which parts of the pipeline are live.
    """
    return runtime.describe()


# ---- uploads ---------------------------------------------------------------


@app.post("/v1/uploads")
async def create_upload(
    file: UploadFile = File(...), runtime: Runtime = Depends(get_runtime)
) -> dict[str, Any]:
    """Accept an image and detect faces, without searching anything yet.

    Splitting this from the verification lets the UI resolve the multi-face
    case up front. No network call leaves the machine at this point.
    """
    data = await file.read()
    upload = await runtime.create_upload(data)
    return upload.to_dict()


# ---- verifications ---------------------------------------------------------


@app.post("/v1/verifications", status_code=202)
async def start_verification(
    body: StartVerificationRequest, runtime: Runtime = Depends(get_runtime)
) -> dict[str, Any]:
    upload = runtime.get_upload(body.upload_id)
    if upload is None:
        raise HTTPException(status_code=404, detail="Upload not found or expired.")
    if upload.requires_selection and body.face_index is None:
        raise HTTPException(
            status_code=400,
            detail=f"{len(upload.faces)} faces detected; face_index is required.",
        )

    run = await runtime.start_run(upload, body.face_index)
    return {
        "verification_id": run.verification_id,
        "events_url": f"/v1/verifications/{run.verification_id}/events",
        "result_url": f"/v1/verifications/{run.verification_id}",
    }


@app.get("/v1/verifications")
async def list_verifications(
    limit: int = Query(50, ge=1, le=200), runtime: Runtime = Depends(get_runtime)
) -> dict[str, Any]:
    return {"runs": runtime.store.list_runs(limit)}


@app.get("/v1/verifications/{verification_id}")
async def get_verification(
    verification_id: str, runtime: Runtime = Depends(get_runtime)
) -> dict[str, Any]:
    result = runtime.result_dict(verification_id)
    if result is None:
        run = runtime.get_run(verification_id)
        if run is not None:
            return {"verification_id": verification_id, "status": "running"}
        raise HTTPException(status_code=404, detail="Verification not found.")
    return result


# ---- event stream ----------------------------------------------------------


def _sse(event_type: str, payload: dict[str, Any]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.get("/v1/verifications/{verification_id}/events")
async def stream_events(
    verification_id: str,
    request: Request,
    replay: bool = Query(False, description="Replay a stored run's event log"),
    speed: float = Query(1.0, ge=0.1, le=20.0, description="Replay speed multiplier"),
    runtime: Runtime = Depends(get_runtime),
) -> StreamingResponse:
    """Stream pipeline events.

    Live runs stream from the in-memory bus (a late subscriber still receives
    the backlog first). `replay=true` re-emits a stored run's log, preserving
    the real gaps between events -- which is why a replay looks like the
    original run instead of a uniform animation.
    """
    run = runtime.get_run(verification_id)

    if run is not None and not replay:
        async def live():
            async for event in run.bus.subscribe():
                if await request.is_disconnected():
                    break
                yield _sse(event.type, event.to_dict())
            yield _sse("stream.closed", {"verification_id": verification_id})

        return StreamingResponse(live(), media_type="text/event-stream", headers=_SSE_HEADERS)

    stored = runtime.store.load(verification_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Verification not found.")

    async def replayed():
        events = stored.events
        previous: Optional[float] = None
        for event in events:
            if await request.is_disconnected():
                break
            at = event.get("at")
            if previous is not None and at is not None:
                # Reproduce the original pacing, capped so a slow network call
                # in the recorded run does not stall the replay for a minute.
                delay = min(max((at - previous) / max(speed, 0.1), 0.0), 2.5)
                if delay > 0:
                    await asyncio.sleep(delay)
            previous = at
            yield _sse(event.get("type", "unknown"), event)
        yield _sse("stream.closed", {"verification_id": verification_id, "replay": True})

    return StreamingResponse(replayed(), media_type="text/event-stream", headers=_SSE_HEADERS)


_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    # Without this, nginx and similar proxies buffer the stream and the UI
    # receives every event at once when the run finishes.
    "X-Accel-Buffering": "no",
}


# ---- evidence and assets ---------------------------------------------------


@app.get("/v1/verifications/{verification_id}/evidence")
async def get_evidence(
    verification_id: str,
    pretty: bool = Query(False),
    runtime: Runtime = Depends(get_runtime),
) -> Response:
    """Return the evidence bundle.

    The default is the canonical bytes -- exactly what was hashed, so
    `sha256sum` on the downloaded file reproduces the anchored digest.
    `pretty=true` returns an indented copy for reading, which will *not* match.
    """
    stored = runtime.store.load(verification_id)
    if stored is None or stored.evidence_canonical is None:
        raise HTTPException(status_code=404, detail="No evidence for this verification.")

    if pretty:
        body = json.dumps(stored.evidence_record, indent=2, sort_keys=True, ensure_ascii=False)
        return Response(content=body, media_type="application/json")

    return Response(
        content=stored.evidence_canonical.encode("utf-8"),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{verification_id}-evidence.json"',
            "X-Evidence-SHA256": sha256_bytes(stored.evidence_canonical.encode("utf-8")),
        },
    )


@app.get("/v1/verifications/{verification_id}/assets/{filename}")
async def get_asset(
    verification_id: str, filename: str, runtime: Runtime = Depends(get_runtime)
) -> Response:
    data = runtime.asset(verification_id, filename)
    if data is None:
        raise HTTPException(status_code=404, detail="Asset not found.")
    media_type = "image/jpeg" if filename.endswith((".jpg", ".jpeg")) else "image/png"
    return Response(content=data, media_type=media_type, headers={"Cache-Control": "public, max-age=3600"})


# ---- integrity and tamper --------------------------------------------------


@app.get("/v1/verifications/{verification_id}/integrity")
async def recheck_integrity(
    verification_id: str, runtime: Runtime = Depends(get_runtime)
) -> dict[str, Any]:
    """Re-run the integrity check now, against the live chain.

    Deliberately re-reads the contract instead of returning the stored report:
    the whole value of an anchor is that anyone can re-verify it later, and
    this endpoint is that check.
    """
    stored = runtime.store.load(verification_id)
    if stored is None or stored.evidence_record is None:
        raise HTTPException(status_code=404, detail="No evidence for this verification.")

    bundle = EvidenceBundle.create(stored.evidence_record)
    anchor = runtime.pipeline.anchor
    onchain_hash: Optional[str] = None
    onchain: Optional[dict[str, Any]] = None
    chain_error: Optional[str] = None

    if anchor.configured:
        try:
            record = await asyncio.to_thread(anchor.read_record, verification_id)
            onchain = record.to_dict()
            onchain_hash = record.evidence_hash
        except RayaError as exc:
            chain_error = exc.message

    report = check_integrity(bundle, onchain_hash, None)
    return {
        "verification_id": verification_id,
        "local_hash": bundle.sha256,
        "onchain": onchain,
        "chain_error": chain_error,
        "integrity": report.to_dict(),
        "checked_at": time.time(),
    }


@app.post("/v1/verifications/{verification_id}/tamper")
async def tamper_test(
    verification_id: str,
    body: TamperRequest,
    runtime: Runtime = Depends(get_runtime),
) -> dict[str, Any]:
    """Alter one evidence field on a copy and show the hash no longer matches.

    The stored evidence is never modified; the demonstration runs against a
    deep copy. Where the run was anchored, the comparison is made against the
    value read back from the chain rather than the local hash, so the check is
    genuinely external.
    """
    stored = runtime.store.load(verification_id)
    if stored is None or stored.evidence_record is None:
        raise HTTPException(status_code=404, detail="No evidence for this verification.")

    bundle = EvidenceBundle.create(stored.evidence_record)
    anchored_hash: Optional[str] = None
    anchor = runtime.pipeline.anchor
    if anchor.configured:
        try:
            record = await asyncio.to_thread(anchor.read_record, verification_id)
            anchored_hash = record.evidence_hash
        except RayaError:
            anchored_hash = None

    try:
        outcome = simulate_tamper(
            bundle,
            field_path=body.field_path,
            new_value=body.new_value,
            anchored_hash=anchored_hash,
        )
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return {
        "verification_id": verification_id,
        "compared_against": "on-chain record" if anchored_hash else "local evidence hash",
        **outcome.to_dict(),
    }


# ---- export ----------------------------------------------------------------


@app.get("/v1/verifications/{verification_id}/export")
async def export_evidence(
    verification_id: str, runtime: Runtime = Depends(get_runtime)
) -> Response:
    """Download a self-contained, independently checkable evidence package."""
    stored = runtime.store.load(verification_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Verification not found.")

    result = stored.result
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        if stored.evidence_canonical:
            archive.writestr("evidence.json", stored.evidence_canonical)
            archive.writestr(
                "evidence.pretty.json",
                json.dumps(stored.evidence_record, indent=2, sort_keys=True, ensure_ascii=False),
            )
        archive.writestr(
            "verification.json", json.dumps(result, indent=2, ensure_ascii=False)
        )
        archive.writestr("events.json", json.dumps(stored.events, indent=2, ensure_ascii=False))
        archive.writestr("integrity.txt", _integrity_text(verification_id, stored))
        archive.writestr("README.txt", _export_readme(verification_id))

    buffer.seek(0)
    return Response(
        content=buffer.read(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{verification_id}-evidence.zip"'
        },
    )


def _integrity_text(verification_id: str, stored) -> str:
    result = stored.result
    evidence = result.get("evidence") or {}
    anchor = result.get("anchor") or {}
    storage = result.get("storage") or {}
    integrity = result.get("integrity") or {}

    lines = [
        "RAYA EVIDENCE INTEGRITY",
        "=" * 60,
        f"Verification    {verification_id}",
        f"Status          {result.get('status')}",
        f"Headline        {result.get('headline')}",
        "",
        f"Evidence SHA256 {evidence.get('sha256', '-')}",
        f"Input SHA256    {(result.get('input') or {}).get('sha256', '-')}",
        f"Source SHA256   {(result.get('match') or {}).get('image_sha256', '-')}",
        f"IPFS CID        {storage.get('cid', '-')}",
        f"Chain           {anchor.get('chain_name', '-')} (id {anchor.get('chain_id', '-')})",
        f"Contract        {anchor.get('contract_address', '-')}",
        f"Transaction     {anchor.get('tx_hash', '-')}",
        f"Block           {anchor.get('block_number', '-')}",
        "",
        f"Integrity       {integrity.get('summary', 'not checked')}",
        "",
        "VERIFY IT YOURSELF",
        "-" * 60,
        "  sha256sum evidence.json",
        "",
        "That digest must equal the Evidence SHA256 above, and the value stored",
        "on chain. evidence.json is the canonical serialization -- the exact",
        "bytes that were hashed. evidence.pretty.json is for reading only and",
        "will produce a different digest.",
        "",
    ]
    for check in integrity.get("checks", []):
        state = "PASS" if check.get("passed") else ("SKIP" if not check.get("performed") else "FAIL")
        lines.append(f"  [{state}] {check.get('label')}")
    return "\n".join(lines) + "\n"


def _export_readme(verification_id: str) -> str:
    return f"""RAYA evidence export -- {verification_id}

evidence.json          Canonical evidence record. These exact bytes were
                       hashed with SHA-256, stored on IPFS and anchored on
                       chain. Verify with: sha256sum evidence.json
evidence.pretty.json   Same record, indented for reading. Different digest.
verification.json      Full run result, including every rejected candidate.
events.json            The pipeline event log this run actually emitted.
integrity.txt          Hashes, anchor details and how to check them.

What this evidence asserts: a face in the input image and a face in an
independently retrieved source image scored at or above the stated similarity
threshold under the named model.

What it does not assert: the identity of any person. Face recognition error
rates vary with image quality and across demographic groups, and a similarity
score is not proof of identity.
"""
