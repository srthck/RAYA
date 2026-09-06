/** Presentation helpers. */

/** Abbreviate a hash for display while keeping both ends recognisable. */
export function shortHash(value: string | null | undefined, head = 8, tail = 6): string {
  if (!value) return "—";
  const clean = value.startsWith("0x") ? value.slice(2) : value;
  if (clean.length <= head + tail) return clean;
  return `${clean.slice(0, head)}…${clean.slice(-tail)}`;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

/**
 * Similarity is always shown to four decimals, never as a percentage.
 * A percentage reads as a probability of identity, which is precisely the
 * claim RAYA does not make.
 */
export function formatSimilarity(value: number | null | undefined): string {
  if (value == null) return "—";
  return value.toFixed(4);
}

export function formatTime(epochSeconds: number | null | undefined): string {
  if (!epochSeconds) return "—";
  return new Date(epochSeconds * 1000).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "medium",
  });
}

export function hostOf(url: string | null | undefined): string {
  if (!url) return "—";
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export type Tone = "verified" | "rejected" | "pending" | "neutral";

export function statusTone(status: string): Tone {
  switch (status) {
    case "verified":
    case "verified_and_anchored":
      return "verified";
    case "rejected":
    case "failed":
    case "invalid_input":
      return "rejected";
    case "verified_not_anchored":
    case "search_unavailable":
    case "multiple_faces":
      return "pending";
    default:
      return "neutral";
  }
}

/** Short, non-euphemistic label for a candidate outcome. */
export function candidateStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    discovered: "Queued",
    not_social: "Not a social source",
    no_image_url: "No image URL",
    unreachable: "Could not retrieve",
    undecodable: "Not a usable image",
    no_face: "No face found",
    face_too_small: "Face too small",
    rejected: "Rejected",
    verified: "Verified",
    error: "Error",
  };
  return labels[status] ?? status;
}

export async function copyText(value: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(value);
    return true;
  } catch {
    return false;
  }
}
