"use client";

/**
 * The input, kept on screen for the whole run.
 *
 * Previously the upload area unmounted the moment a verification started, so
 * the thing being verified vanished from the workstation. The input is the
 * first artifact in the chain of custody and its digest is what every later
 * claim refers to, so it stays visible.
 *
 * The digest shown is of the exact original bytes the user supplied. It is
 * never the search derivative, and never a re-encoded copy.
 */

import { motion } from "framer-motion";

import { CopyHash, Field, Status, type StatusWord } from "@/components/atoms";
import { formatBytes } from "@/lib/format";
import type { UploadResult } from "@/lib/types";

export function InputEvidence({
  upload,
  previewUrl,
  fileName,
  status,
}: {
  upload: UploadResult;
  previewUrl: string | null;
  fileName: string | null;
  status: StatusWord;
}) {
  return (
    <motion.section
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
      aria-label="Input evidence"
      style={{ display: "grid", gap: "var(--s4)" }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          gap: "var(--s2)",
        }}
      >
        <span className="label">Input evidence</span>
        <Status value={status} />
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0, 200px) minmax(0, 1fr)",
          gap: "var(--s5)",
          alignItems: "start",
        }}
        className="input-evidence-grid"
      >
        <div
          style={{
            position: "relative",
            borderRadius: "var(--radius-lg)",
            overflow: "hidden",
            border: "1px solid var(--line)",
            background: "var(--bg-sunken)",
            aspectRatio: `${upload.width} / ${upload.height}`,
            maxHeight: 260,
            boxShadow: "var(--shadow)",
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

          {/* The detector's own box, in its own coordinates, as a percentage so
              it tracks the rendered size. */}
          {upload.faces.map((face) => {
            const [x, y, w, h] = face.bbox;
            return (
              <span
                key={face.index}
                aria-hidden
                style={{
                  position: "absolute",
                  left: `${(x / upload.width) * 100}%`,
                  top: `${(y / upload.height) * 100}%`,
                  width: `${(w / upload.width) * 100}%`,
                  height: `${(h / upload.height) * 100}%`,
                  border: "1.5px solid var(--verified)",
                  borderRadius: 3,
                  boxShadow: "0 0 0 1px rgba(255,255,255,0.5)",
                }}
              />
            );
          })}
        </div>

        <div style={{ display: "grid", gap: "var(--s4)", minWidth: 0 }}>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fit, minmax(110px, 1fr))",
              gap: "var(--s4)",
            }}
          >
            <Field label="File" value={fileName ?? "—"} />
            <Field label="Type" value={upload.format} />
            <Field label="Dimensions" value={`${upload.width} × ${upload.height}`} />
            <Field label="Size" value={formatBytes(upload.byte_size)} />
            <Field
              label="Face"
              value={upload.face_count === 0 ? "none usable" : `${upload.face_count} detected`}
              tone={upload.face_count === 0 ? "rejected" : "verified"}
            />
          </div>

          <div>
            <span className="label">Input SHA-256</span>
            <div style={{ marginTop: 4 }}>
              <CopyHash value={upload.sha256} display={upload.sha256} />
            </div>
            <p
              className="mono"
              style={{ margin: "6px 0 0", fontSize: 10.5, color: "var(--ink-quaternary)" }}
            >
              Original bytes · hashed locally before any processing
            </p>
          </div>
        </div>
      </div>
    </motion.section>
  );
}
