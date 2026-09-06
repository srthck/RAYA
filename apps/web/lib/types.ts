/**
 * Shapes returned by the RAYA API.
 *
 * These mirror the Python dataclasses exactly. Keeping them explicit rather
 * than `any` is what lets the UI be honest: an unanchored run has
 * `anchor: null`, and the type system forces every screen to handle that case
 * instead of rendering a confident-looking blank.
 */

export type RunStatus =
  | "verified_and_anchored"
  | "verified_not_anchored"
  | "no_verified_match"
  | "no_social_candidates"
  | "no_search_results"
  | "no_face_detected"
  | "multiple_faces"
  | "face_unusable"
  | "search_unavailable"
  | "invalid_input"
  | "failed"
  | "running";

export type CandidateStatus =
  | "discovered"
  | "not_social"
  | "no_image_url"
  | "unreachable"
  | "undecodable"
  | "no_face"
  | "face_too_small"
  | "rejected"
  | "verified"
  | "error";

export interface FaceQuality {
  size_px: number;
  relative_area: number;
  sharpness: number;
  brightness: number;
  detector_score: number;
}

export interface DetectedFace {
  index: number;
  bbox: [number, number, number, number];
  landmarks: [number, number][];
  score: number;
  quality: FaceQuality;
}

export interface Verdict {
  similarity: number | null;
  threshold: number;
  metric: string;
  passed: boolean;
}

export interface Candidate {
  id: string;
  position: number;
  title: string | null;
  page_url: string | null;
  image_url: string | null;
  thumbnail_url: string | null;
  source_name: string | null;
  platform: string;
  platform_label: string;
  is_social: boolean;
  is_post_url: boolean;
  status: CandidateStatus;
  reason: string | null;
  image_sha256: string | null;
  image_bytes: number | null;
  image_mime: string | null;
  image_width: number | null;
  image_height: number | null;
  fetched_url: string | null;
  http_status: number | null;
  face_count: number | null;
  face_quality: FaceQuality | null;
  verdict: Verdict | null;
  duration_ms: number | null;
  has_preview: boolean;
}

export interface IntegrityCheck {
  name: string;
  label: string;
  performed: boolean;
  passed: boolean | null;
  expected: string | null;
  actual: string | null;
  detail: string | null;
}

export interface IntegrityReport {
  verified: boolean;
  anchored: boolean;
  summary: string;
  checks: IntegrityCheck[];
}

export interface AnchorReceipt {
  tx_hash: string;
  block_number: number;
  block_hash: string;
  gas_used: number;
  effective_gas_price: number | null;
  chain_id: number;
  chain_name: string;
  contract_address: string;
  submitter: string;
  explorer_tx_url: string;
  explorer_address_url: string;
  confirmed_at: number;
  duration_ms: number;
}

export interface StoredEvidence {
  cid: string;
  provider: string;
  size: number;
  published: boolean;
  gateway_url: string | null;
  detail: string | null;
}

export interface StageError {
  stage: string;
  code: string;
  message: string;
  fatal: boolean;
}

export interface SearchCopy {
  sha256: string;
  mime: string;
  width: number;
  height: number;
  byte_size: number;
  max_edge: number;
  jpeg_quality: number;
  resized: boolean;
  note: string;
}

export interface VerificationResult {
  verification_id: string;
  created_at: number;
  status: RunStatus;
  headline: string;
  is_match: boolean;
  input: {
    sha256: string;
    byte_size: number;
    mime: string;
    width: number;
    height: number;
    format?: string;
    face?: DetectedFace;
    ipfs_cid?: string;
  };
  faces: DetectedFace[];
  selected_face_index: number | null;
  search_copy: SearchCopy | null;
  search: {
    provider: string;
    query_image_url: string;
    queried_at: number;
    duration_ms: number;
    result_count: number;
    raw_result_count: number;
    metadata: Record<string, unknown>;
  } | null;
  counts: {
    results: number;
    social: number;
    compared: number;
    verified: number;
    rejected: number;
  };
  candidates?: Candidate[];
  match: Candidate | null;
  similarity: number | null;
  evidence: { sha256: string; byte_size: number; schema_version: string } | null;
  storage: StoredEvidence | null;
  anchor: AnchorReceipt | null;
  onchain: {
    evidence_hash: string;
    input_hash: string;
    source_hash: string;
    cid: string;
    similarity: number;
    anchored_at: number;
    submitter: string;
  } | null;
  integrity: IntegrityReport | null;
  errors: StageError[];
  duration_ms: number | null;
}

export interface UploadResult {
  upload_id: string;
  sha256: string;
  width: number;
  height: number;
  mime: string;
  format: string;
  byte_size: number;
  face_count: number;
  faces: DetectedFace[];
  requires_selection: boolean;
}

export interface RayaConfig {
  // `model_sha256` identifies the exact weight file, so a published similarity
  // is reproducible by anyone holding the same models.
  detector: { name: string; version: string; model_sha256?: string | null };
  encoder: {
    name: string;
    version: string;
    dim: number;
    metric: string;
    model_sha256?: string | null;
  };
  threshold: number;
  metric: string;
  search: {
    provider: string;
    display_name: string;
    configured: boolean;
    supports_direct_upload?: boolean;
  };
  storage: { provider: string; configured: boolean };
  chain: {
    provider: string;
    chain_name: string;
    chain_id: number;
    rpc_url: string;
    explorer: string;
    contract_address: string | null;
    configured: boolean;
  };
  limits: {
    max_upload_bytes: number;
    max_candidates: number;
    max_verified_candidates: number;
    min_face_size_px: number;
  };
}

export interface TamperResult {
  verification_id: string;
  compared_against: string;
  field_path: string;
  original_value: unknown;
  tampered_value: unknown;
  original_hash: string;
  tampered_hash: string;
  anchored_hash: string | null;
  detected: boolean;
  summary: string;
}

export interface RayaEvent {
  seq: number;
  type: string;
  at: number;
  data: Record<string, any>;
}
