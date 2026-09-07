"use client";

/**
 * Derives the whole workspace UI from the backend event stream.
 *
 * This hook is the reason RAYA has no fake progress bars. Every stage, every
 * candidate tile and every hash on screen is written here in response to an
 * event the pipeline actually emitted. If the backend never reaches the anchor
 * stage, the anchor stage never lights up -- there is no timer that could
 * advance it.
 *
 * The same reducer drives `/replay/[id]`: replay is the stored event log
 * re-emitted at its original pacing, so it exercises this identical code path
 * rather than a separate animation.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "./api";
import type { Candidate, DetectedFace, RayaEvent, VerificationResult } from "./types";

export type StageId =
  | "input"
  | "face"
  | "discover"
  | "verify"
  | "evidence"
  | "anchor"
  | "readback"
  | "integrity";

export type StageState = "idle" | "active" | "done" | "failed" | "skipped";

export interface Stage {
  id: StageId;
  label: string;
  state: StageState;
  detail?: string;
}

/**
 * The eight stages, in pipeline order.
 *
 * Discovery, verification, anchoring and integrity are deliberately separate
 * steps rather than one "verified" bar: each makes a different claim, and
 * collapsing them is exactly the overstatement RAYA exists to avoid.
 */
export const STAGE_ORDER: { id: StageId; label: string }[] = [
  { id: "input", label: "Input" },
  { id: "face", label: "Face" },
  { id: "discover", label: "Discover" },
  { id: "verify", label: "Verify" },
  { id: "evidence", label: "Evidence" },
  { id: "anchor", label: "Anchor" },
  { id: "readback", label: "Read-back" },
  { id: "integrity", label: "Integrity" },
];

export interface PipelineState {
  connected: boolean;
  finished: boolean;
  stages: Record<StageId, Stage>;
  currentStage: StageId;

  input?: { sha256: string; width: number; height: number; byte_size: number; mime: string };
  faces: DetectedFace[];
  selectedFace?: DetectedFace;
  encoder?: { model: string; dim: number };

  searchProvider?: string;
  searchCopy?: {
    sha256: string;
    byteSize: number;
    width: number;
    height: number;
    quality: number;
    resized: boolean;
  };
  searchMethod?: string;
  searchPreparing?: { method: string; cid?: string; url?: string };
  searchCounts?: { results: number; raw: number; durationMs: number; isReplay: boolean };

  candidates: Candidate[];
  evaluating: Set<string>;
  match?: Candidate;

  evidence?: { sha256: string; byteSize: number; schemaVersion: string };
  storage?: { cid: string; published: boolean; gatewayUrl: string | null; provider: string };
  anchor?: {
    txHash: string;
    blockNumber: number;
    explorerTxUrl: string;
    contractAddress: string;
    chainName: string;
    gasUsed: number;
  };
  readback?: { onchainHash: string; localHash: string; matches: boolean };
  integrity?: { verified: boolean; anchored: boolean; summary: string };

  failure?: { code: string; message: string; stage?: string };
  warnings: { stage: string; message: string }[];
  events: RayaEvent[];
}

function emptyStages(): Record<StageId, Stage> {
  return STAGE_ORDER.reduce(
    (acc, s) => {
      acc[s.id] = { id: s.id, label: s.label, state: "idle" };
      return acc;
    },
    {} as Record<StageId, Stage>,
  );
}

export function initialState(): PipelineState {
  return {
    connected: false,
    finished: false,
    stages: emptyStages(),
    currentStage: "input",
    faces: [],
    candidates: [],
    evaluating: new Set(),
    warnings: [],
    events: [],
  };
}

/** Map an event onto the next UI state. Pure, so replay and live are identical. */
export function reduceEvent(prev: PipelineState, event: RayaEvent): PipelineState {
  const next: PipelineState = {
    ...prev,
    events: [...prev.events, event],
    stages: { ...prev.stages },
    evaluating: new Set(prev.evaluating),
  };
  const d = event.data ?? {};

  const mark = (id: StageId, state: StageState, detail?: string) => {
    next.stages[id] = { ...next.stages[id], state, detail };
    if (state === "active") next.currentStage = id;
  };

  switch (event.type) {
    case "pipeline.started":
      mark("input", "active");
      next.searchProvider = d.provider;
      next.encoder = { model: d.encoder?.name, dim: d.encoder?.dim };
      break;

    case "input.hashed":
      next.input = {
        sha256: d.sha256,
        width: d.width,
        height: d.height,
        byte_size: d.byte_size,
        mime: d.mime,
      };
      mark("input", "done", `${d.width}x${d.height}`);
      break;

    case "face.detecting":
      mark("face", "active");
      break;

    case "face.detected":
      next.faces = d.faces ?? [];
      mark("face", "active", `${d.face_count} detected`);
      break;

    case "face.selected":
      next.selectedFace = d.face;
      break;

    case "face.encoded":
      mark("face", "done", `${d.model} - ${d.dim}d`);
      break;

    case "search.preparing":
      mark("discover", "active", "building search copy");
      next.searchMethod = d.method;
      if (d.search_copy) {
        next.searchCopy = {
          sha256: d.search_copy.sha256,
          byteSize: d.search_copy.byte_size,
          width: d.search_copy.width,
          height: d.search_copy.height,
          quality: d.search_copy.jpeg_quality,
          resized: d.search_copy.resized,
        };
      }
      break;

    case "search.started":
      mark("discover", "active", d.display_name ?? d.provider);
      next.searchProvider = d.provider;
      next.searchMethod = d.method ?? next.searchMethod;
      break;

    case "search.completed":
      next.searchCounts = {
        results: d.result_count,
        raw: d.raw_result_count,
        durationMs: d.duration_ms,
        isReplay: Boolean(d.is_replay),
      };
      mark("discover", "done", `${d.result_count} discovered`);
      break;

    case "candidate.discovered":
      next.candidates = [...next.candidates, d.candidate as Candidate];
      break;

    case "candidate.classified":
      mark("verify", "active", `${d.eligible} eligible of ${d.total}`);
      break;

    case "candidate.evaluating":
      next.evaluating.add(d.candidate_id);
      break;

    case "candidate.verified":
    case "candidate.rejected": {
      const updated = d.candidate as Candidate;
      next.evaluating.delete(updated.id);
      next.candidates = next.candidates.map((c) => (c.id === updated.id ? updated : c));
      break;
    }

    case "match.selected":
      next.match = d.candidate as Candidate;
      mark("verify", "done", `similarity ${Number(d.candidate?.verdict?.similarity).toFixed(4)}`);
      break;

    case "evidence.created":
      mark("evidence", "active");
      break;

    case "evidence.hashed":
      next.evidence = {
        sha256: d.sha256,
        byteSize: prev.evidence?.byteSize ?? 0,
        schemaVersion: prev.evidence?.schemaVersion ?? "1.0",
      };
      mark("evidence", "done", "sha-256");
      break;

    case "ipfs.uploading":
      mark("evidence", "active", "storing on ipfs");
      break;

    case "ipfs.uploaded":
      next.storage = {
        cid: d.cid,
        published: d.published,
        gatewayUrl: d.gateway_url ?? null,
        provider: d.provider,
      };
      mark("evidence", "done", d.published ? "stored on ipfs" : "stored locally");
      break;

    case "blockchain.submitting":
      mark("anchor", "active", d.chain);
      break;

    case "blockchain.submitted":
      mark("anchor", "active", "submitted, awaiting confirmation");
      break;

    case "blockchain.confirmed":
      mark("anchor", "done", `block ${d.block_number}`);
      next.anchor = {
        txHash: d.tx_hash,
        blockNumber: d.block_number,
        explorerTxUrl: d.explorer_tx_url,
        contractAddress: d.contract_address,
        chainName: d.chain_name,
        gasUsed: d.gas_used,
      };
      break;

    case "readback.started":
      mark("readback", "active", "reading contract state");
      break;

    case "readback.completed":
      next.readback = {
        onchainHash: d.onchain_evidence_hash,
        localHash: d.local_evidence_hash,
        matches: Boolean(d.matches),
      };
      mark("readback", d.matches ? "done" : "failed", d.matches ? "hashes match" : "hash mismatch");
      break;

    case "integrity.checking":
      mark("integrity", "active");
      break;

    case "integrity.verified":
      next.integrity = { verified: true, anchored: d.anchored, summary: d.summary };
      mark("integrity", "done", "verified");
      break;

    case "integrity.failed":
      next.integrity = {
        verified: Boolean(d.verified),
        anchored: Boolean(d.anchored),
        summary: d.summary,
      };
      // A check that ran did not pass. This is the only integrity outcome that
      // is genuinely a failure.
      mark("integrity", "failed", "hash mismatch");
      break;

    case "integrity.inconclusive":
      next.integrity = {
        verified: Boolean(d.verified),
        anchored: Boolean(d.anchored),
        summary: d.summary,
      };
      // Nothing failed, but there was no anchor to compare against. The rail
      // gets a short phrase of its own rather than a truncated summary: in a
      // ~150px column, "Integrity verified: the ..." reads as though the chain
      // comparison had passed, directly under "Anchor: not run".
      mark("integrity", "skipped", "not anchored");
      break;

    case "stage.failed": {
      next.warnings = [...next.warnings, { stage: d.stage, message: d.message }];
      const stageMap: Record<string, StageId> = {
        search_prepare: "discover",
        search: "discover",
        ipfs: "evidence",
        anchor: "anchor",
        readback: "readback",
        ipfs_readback: "integrity",
      };
      const target = stageMap[d.stage as string];
      if (target) {
        // A stage that was never attempted because a credential is missing is
        // "skipped", not "failed" -- an unconfigured deployment must not
        // render as a broken one. The backend sends the error code, so this is
        // decided on the code rather than by pattern-matching English prose.
        // Codes meaning "this stage was never attempted". A *rejected*
        // credential is not here: the provider was called and refused, which
        // is a failure, and labelling it "not configured" would contradict the
        // reason shown beside it.
        const NEVER_RAN = new Set([
          "chain_not_configured",
          "search_provider_not_configured",
          "no_public_url",
          "storage_error",
        ]);
        mark(target, NEVER_RAN.has(String(d.code)) ? "skipped" : "failed", d.message);
      }
      break;
    }

    case "verification.failed":
      next.failure = { code: d.code, message: d.message };
      next.finished = true;
      if (d.code === "no_face_detected" || d.code === "multiple_faces") {
        mark("face", "failed", d.message);
      }
      if (d.faces) next.faces = d.faces;
      break;

    case "verification.completed":
      next.finished = true;
      break;

    default:
      break;
  }

  return next;
}

interface Options {
  replay?: boolean;
  speed?: number;
  enabled?: boolean;
}

export function usePipeline(verificationId: string | null, options: Options = {}) {
  const { replay = false, speed = 1, enabled = true } = options;
  const [state, setState] = useState<PipelineState>(initialState);
  const [result, setResult] = useState<VerificationResult | null>(null);
  const sourceRef = useRef<EventSource | null>(null);

  const reset = useCallback(() => {
    setState(initialState());
    setResult(null);
  }, []);

  useEffect(() => {
    if (!verificationId || !enabled) return;

    setState(initialState());
    const source = new EventSource(api.eventsUrl(verificationId, replay, speed));
    sourceRef.current = source;

    source.onopen = () => setState((s) => ({ ...s, connected: true }));

    // Named SSE events do not reach `onmessage`, so each type is subscribed
    // individually. The list mirrors EventType in core/raya/events.py.
    const types = [
      "pipeline.started",
      "input.received",
      "input.hashed",
      "face.detecting",
      "face.detected",
      "face.selected",
      "face.encoded",
      "search.preparing",
      "search.started",
      "search.completed",
      "candidate.discovered",
      "candidate.classified",
      "candidate.evaluating",
      "candidate.fetched",
      "candidate.face_found",
      "candidate.compared",
      "candidate.verified",
      "candidate.rejected",
      "match.selected",
      "evidence.created",
      "evidence.hashed",
      "ipfs.uploading",
      "ipfs.uploaded",
      "blockchain.submitting",
      "blockchain.submitted",
      "blockchain.confirmed",
      "readback.started",
      "readback.completed",
      "integrity.checking",
      "integrity.verified",
      "integrity.failed",
      "integrity.inconclusive",
      "stage.failed",
      "verification.completed",
      "verification.failed",
    ];

    const handler = (raw: MessageEvent) => {
      try {
        setState((prev) => reduceEvent(prev, JSON.parse(raw.data) as RayaEvent));
      } catch {
        /* a malformed frame must not tear down the stream */
      }
    };

    types.forEach((t) => source.addEventListener(t, handler as EventListener));

    const onClosed = () => {
      source.close();
      setState((s) => ({ ...s, connected: false, finished: true }));
      // The stream is the live view; the result endpoint is the authoritative
      // record, so it is fetched once the run ends.
      api.result(verificationId).then(setResult).catch(() => undefined);
    };
    source.addEventListener("stream.closed", onClosed);

    source.onerror = () => {
      // EventSource retries on its own; only a closed stream is terminal.
      if (source.readyState === EventSource.CLOSED) onClosed();
    };

    return () => {
      types.forEach((t) => source.removeEventListener(t, handler as EventListener));
      source.removeEventListener("stream.closed", onClosed);
      source.close();
      sourceRef.current = null;
    };
  }, [verificationId, replay, speed, enabled]);

  const socialCandidates = useMemo(
    () => state.candidates.filter((c) => c.is_social),
    [state.candidates],
  );

  return { state, result, socialCandidates, reset };
}
