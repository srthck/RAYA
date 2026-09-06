/**
 * Client for the RAYA API.
 *
 * Requests go to the same origin under `/api`, which `next.config.mjs` rewrites
 * to the backend. That keeps `EventSource` -- which has no CORS escape hatch
 * and carries the entire live UI -- on a same-origin URL.
 */

import type {
  RayaConfig,
  TamperResult,
  UploadResult,
  VerificationResult,
} from "./types";

const BASE = "/api/v1";

export class ApiError extends Error {
  code: string;
  status: number;
  detail: unknown;

  constructor(message: string, code: string, status: number, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, init);
  } catch {
    throw new ApiError(
      "Could not reach the RAYA API. Is the backend running on port 8000?",
      "network_error",
      0,
    );
  }

  if (!response.ok) {
    let code = "http_error";
    let message = `Request failed with HTTP ${response.status}.`;
    try {
      const body = await response.json();
      // The backend returns typed pipeline errors as {error: {code, message}}
      // and FastAPI validation errors as {detail}. Both are surfaced verbatim
      // so the UI never invents an explanation.
      if (body?.error) {
        code = body.error.code ?? code;
        message = body.error.message ?? message;
      } else if (typeof body?.detail === "string") {
        message = body.detail;
      }
    } catch {
      /* a non-JSON error body leaves the defaults in place */
    }
    throw new ApiError(message, code, response.status);
  }

  return (await response.json()) as T;
}

export const api = {
  config: () => request<RayaConfig>("/config"),

  health: () => request<{ status: string; version: string }>("/health"),

  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<UploadResult>("/uploads", { method: "POST", body: form });
  },

  startVerification: (uploadId: string, faceIndex: number | null) =>
    request<{ verification_id: string; events_url: string; result_url: string }>(
      "/verifications",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ upload_id: uploadId, face_index: faceIndex }),
      },
    ),

  result: (id: string) => request<VerificationResult>(`/verifications/${id}`),

  list: () =>
    request<{ runs: Array<Record<string, unknown>> }>("/verifications"),

  integrity: (id: string) =>
    request<{
      verification_id: string;
      local_hash: string;
      onchain: Record<string, unknown> | null;
      chain_error: string | null;
      integrity: VerificationResult["integrity"];
      checked_at: number;
    }>(`/verifications/${id}/integrity`),

  tamper: (id: string, fieldPath = "match.similarity") =>
    request<TamperResult>(`/verifications/${id}/tamper`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ field_path: fieldPath }),
    }),

  evidenceUrl: (id: string, pretty = false) =>
    `${BASE}/verifications/${id}/evidence${pretty ? "?pretty=true" : ""}`,

  exportUrl: (id: string) => `${BASE}/verifications/${id}/export`,

  assetUrl: (id: string, filename: string) =>
    `${BASE}/verifications/${id}/assets/${filename}`,

  eventsUrl: (id: string, replay = false, speed = 1) =>
    `${BASE}/verifications/${id}/events${replay ? `?replay=true&speed=${speed}` : ""}`,
};
