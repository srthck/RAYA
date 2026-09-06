"use client";

/**
 * The input, kept on screen for the whole run.
 *
 * Driven from pipeline state so it renders identically for a live run and for
 * a replay, where the browser no longer holds the original file. When a live
 * upload is available its preview and filename are used; otherwise the run's
 * stored face crop stands in.
 *
 * The digest shown is of the exact original bytes. It is never the search
 * derivative and never a re-encoded copy.
 */

import { CopyHash, Field } from "@/components/atoms";
import { formatBytes } from "@/lib/format";
import type { UploadResult } from "@/lib/types";
import type { PipelineState } from "@/lib/usePipeline";

export function InputEvidence({
  state,
  upload,
  previewUrl,
  fileName,
}: {
  state: PipelineState;
  upload: UploadResult | null;
  previewUrl: string | null;
  fileName: string | null;
}) {
  const input = state.input;
  const faces = state.faces;
  // A live upload knows the true pixel dimensions; a replay reads them from
  // the recorded input metadata.
  const width = upload?.width ?? input?.width ?? 0;
  const height = upload?.height ?? input?.height ?? 0;

  if (!input && !upload) return null;

  return (
    <div
      className="input-evidence-grid"
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(0, 210px) minmax(0, 1fr)",
        gap: "var(--s5)",
        alignItems: "start",
      }}
    >
      <div
        style={{
          position: "relative",
          borderRadius: "var(--radius)",
          overflow: "hidden",
          border: "1px solid var(--line-strong)",
          background: "var(--bg-sunken)",
          aspectRatio: width && height ? `${width} / ${height}` : "4 / 5",
          maxHeight: 270,
        }}
      >
        {previewUrl && (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={previewUrl}
            alt={`Input image${fileName ? `: ${fileName}` : ""}`}
            style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
          />
        )}

        {/* The detector's own box, in full-image coordinates. Only drawn when
            the preview IS the full image -- a replay shows the stored face
            crop instead, where these coordinates would land nowhere near the
            face. */}
        {previewUrl &&
          upload &&
          width > 0 &&
          faces.map((face) => {
            const [x, y, w, h] = face.bbox;
            return (
              <span
                key={face.index}
                aria-hidden
                style={{
                  position: "absolute",
                  left: `${(x / width) * 100}%`,
                  top: `${(y / height) * 100}%`,
                  width: `${(w / width) * 100}%`,
                  height: `${(h / height) * 100}%`,
                  border: "1.5px solid var(--accent)",
                  borderRadius: 2,
                  boxShadow: "0 0 0 1px rgba(255,255,255,0.55)",
                }}
              />
            );
          })}
      </div>

      <div style={{ display: "grid", gap: "var(--s5)", minWidth: 0 }}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(104px, 1fr))",
            gap: "var(--s4)",
          }}
        >
          {fileName && <Field label="File" value={fileName} />}
          <Field label="Type" value={upload?.format ?? input?.mime ?? "—"} />
          <Field
            label="Dimensions"
            value={width && height ? `${width} × ${height}` : "—"}
          />
          <Field label="Size" value={formatBytes(upload?.byte_size ?? input?.byte_size)} />
          <Field
            label="Face"
            value={faces.length === 0 ? "none usable" : `${faces.length} detected`}
            tone={faces.length === 0 ? "rejected" : "verified"}
          />
        </div>

        <div style={{ minWidth: 0 }}>
          <span className="label">Input SHA-256</span>
          <div style={{ marginTop: 4 }}>
            <CopyHash
              value={upload?.sha256 ?? input?.sha256}
              display={upload?.sha256 ?? input?.sha256 ?? "—"}
            />
          </div>
          {/* Inside the sheet, where it has a white ground to sit on. Over the
              photograph this was barely legible. */}
          <p
            className="mono"
            style={{ margin: "6px 0 0", fontSize: 10.5, color: "var(--ink-tertiary)" }}
          >
            Original bytes · hashed locally before any processing
          </p>
        </div>
      </div>
    </div>
  );
}
