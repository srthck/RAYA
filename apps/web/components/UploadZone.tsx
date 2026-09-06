"use client";

/**
 * Upload, then face selection.
 *
 * Detection runs on upload, before any search. When several faces are present
 * RAYA stops and asks which one is the subject: guessing would silently decide
 * whose identity is being investigated, and the user would never know a choice
 * was made on their behalf.
 */

import { useCallback, useRef, useState } from "react";
import { motion } from "framer-motion";

import { CopyHash, Empty, Field, Status } from "@/components/atoms";
import { api, ApiError } from "@/lib/api";
import { formatBytes } from "@/lib/format";
import type { UploadResult } from "@/lib/types";

interface Props {
  /** The page keeps the upload and its preview so the input stays visible
      for the whole run, instead of unmounting with this component. */
  onStart: (
    verificationId: string,
    context: { upload: UploadResult; previewUrl: string | null; fileName: string | null },
  ) => void;
  disabled?: boolean;
  disabledReason?: string;
}

export function UploadZone({ onStart, disabled, disabledReason }: Props) {
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [upload, setUpload] = useState<UploadResult | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFile = useCallback(async (file: File) => {
    setError(null);
    setBusy(true);
    setUpload(null);
    setSelected(null);
    setFile(file);
    try {
      const objectUrl = URL.createObjectURL(file);
      setPreview((old) => {
        if (old) URL.revokeObjectURL(old);
        return objectUrl;
      });

      const result = await api.upload(file);
      setUpload(result);
      if (!result.requires_selection && result.face_count === 1) setSelected(0);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Upload failed. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }, []);

  const begin = async () => {
    if (!upload) return;
    setBusy(true);
    setError(null);
    try {
      const { verification_id } = await api.startVerification(
        upload.upload_id,
        upload.requires_selection ? selected : null,
      );
      onStart(verification_id, {
        upload,
        previewUrl: preview,
        fileName: file?.name ?? null,
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start verification.");
      setBusy(false);
    }
  };

  const noFace = upload && upload.face_count === 0;
  const ready = upload && upload.face_count > 0 && (!upload.requires_selection || selected !== null);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "var(--s5)" }}>
      {!upload && (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragging(false);
            const file = e.dataTransfer.files?.[0];
            if (file) handleFile(file);
          }}
          onClick={() => inputRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") inputRef.current?.click();
          }}
          style={{
            border: `1px ${dragging ? "solid" : "dashed"} ${dragging ? "var(--accent)" : "var(--line-strong)"}`,
            borderRadius: "var(--radius-lg)",
            // A readability surface: the drop zone sits over a photograph, and
            // transparent text on water is unreadable. Translucent rather than
            // opaque, so the environment still shows through.
            background: dragging
              ? "rgba(232, 246, 253, 0.92)"
              : "rgba(255, 255, 255, 0.82)",
            backdropFilter: "blur(12px) saturate(1.15)",
            WebkitBackdropFilter: "blur(12px) saturate(1.15)",
            boxShadow: dragging ? "var(--shadow-lift)" : "var(--shadow)",
            padding: "clamp(56px, 16vh, 140px) var(--s5)",
            textAlign: "center",
            cursor: busy ? "wait" : "pointer",
            transition:
              "background var(--dur) var(--ease), border-color var(--dur) var(--ease), box-shadow var(--dur) var(--ease)",
          }}
        >
          <p className="label" style={{ marginBottom: "var(--s3)" }}>
            Input evidence
          </p>
          <p className="h2" style={{ fontWeight: 460 }}>
            {busy ? "Reading image…" : "Drop an image"}
          </p>
          <p className="body" style={{ marginTop: "var(--s2)", fontSize: 13.5 }}>
            or click to choose a file · JPEG, PNG, WebP
          </p>
          <p
            className="mono"
            style={{ marginTop: "var(--s4)", fontSize: 11, color: "var(--ink-quaternary)" }}
          >
            Hashed locally before anything else happens.
          </p>
          <input
            ref={inputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/bmp,image/tiff"
            hidden
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleFile(file);
            }}
          />
        </motion.div>
      )}

      {upload && (
        <motion.div
          initial={{ opacity: 0, scale: 0.99 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
          style={{ display: "grid", gap: "var(--s5)" }}
        >
          <div
            style={{
              position: "relative",
              borderRadius: "var(--radius-lg)",
              overflow: "hidden",
              border: "1px solid var(--line)",
              background: "var(--bg-sunken)",
              maxHeight: 460,
              display: "flex",
              justifyContent: "center",
            }}
          >
            {preview && (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={preview}
                alt="Uploaded image"
                style={{ maxHeight: 460, maxWidth: "100%", objectFit: "contain", display: "block" }}
              />
            )}

            {/* Boxes are drawn from the detector's own coordinates, expressed
                as percentages so they track the rendered size. */}
            {upload.faces.map((face) => {
              const [x, y, w, h] = face.bbox;
              const active = selected === face.index;
              return (
                <button
                  key={face.index}
                  type="button"
                  onClick={() => setSelected(face.index)}
                  aria-label={`Select face ${face.index + 1}`}
                  style={{
                    position: "absolute",
                    left: `${(x / upload.width) * 100}%`,
                    top: `${(y / upload.height) * 100}%`,
                    width: `${(w / upload.width) * 100}%`,
                    height: `${(h / upload.height) * 100}%`,
                    border: `2px solid ${active ? "var(--verified)" : "rgba(255,255,255,0.9)"}`,
                    background: "transparent",
                    borderRadius: 2,
                    cursor: upload.requires_selection ? "pointer" : "default",
                    boxShadow: active ? "0 0 0 2px rgba(47,107,79,0.28)" : "none",
                    padding: 0,
                  }}
                />
              );
            })}
          </div>

          {/* The input as evidence: exactly what was accepted, and the digest
              of the exact original bytes -- never of a resized copy. */}
          <div style={{ display: "grid", gap: "var(--s4)" }}>
            <div
              style={{
                display: "flex",
                alignItems: "baseline",
                justifyContent: "space-between",
                gap: "var(--s2)",
              }}
            >
              <span className="label">Input</span>
              <Status
                value={
                  busy ? "RUNNING" : upload.face_count === 0 ? "FAILED" : "COMPLETE"
                }
              />
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
                gap: "var(--s4)",
              }}
            >
              <Field label="File" value={file?.name ?? "—"} />
              <Field label="Type" value={upload.format} />
              <Field label="Dimensions" value={`${upload.width} × ${upload.height}`} />
              <Field label="Size" value={formatBytes(upload.byte_size)} />
              <Field
                label="Face"
                value={
                  upload.face_count === 0
                    ? "no usable face"
                    : `${upload.face_count} detected`
                }
                tone={upload.face_count === 0 ? "rejected" : "verified"}
              />
            </div>

            <Field
              label="Input SHA-256"
              value={<CopyHash value={upload.sha256} display={upload.sha256} />}
            />
          </div>

          <div
            style={{
              display: "flex",
              gap: "var(--s5)",
              flexWrap: "wrap",
              alignItems: "center",
              justifyContent: "space-between",
            }}
          >
            <div style={{ display: "flex", gap: "var(--s2)", marginLeft: "auto" }}>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => {
                  setUpload(null);
                  setSelected(null);
                  setError(null);
                }}
              >
                Choose another
              </button>
              <button
                type="button"
                className="btn btn-sm"
                disabled={!ready || busy || disabled}
                onClick={begin}
                title={disabled ? disabledReason : undefined}
              >
                {busy ? "Starting…" : "Verify"}
              </button>
            </div>
          </div>

          {noFace && (
            <p style={{ color: "var(--rejected)", fontSize: 13.5, margin: 0 }}>
              No usable face detected. RAYA verifies faces, so there is nothing
              to search for in this image.
            </p>
          )}

          {upload.requires_selection && (
            <div
              className="card"
              style={{ padding: "var(--s4)", borderColor: "var(--pending)" }}
            >
              <p style={{ margin: 0, fontSize: 13.5, fontWeight: 560 }}>
                {upload.face_count} faces detected — select a subject.
              </p>
              <p className="body" style={{ marginTop: 4, fontSize: 13 }}>
                RAYA will not pick one for you. Click a face in the image above.
                {selected !== null && (
                  <span style={{ color: "var(--verified)" }}>
                    {" "}
                    Face {selected + 1} selected.
                  </span>
                )}
              </p>
            </div>
          )}

          {disabled && disabledReason && (
            <Empty>{disabledReason}</Empty>
          )}
        </motion.div>
      )}

      {error && (
        <p style={{ color: "var(--rejected)", fontSize: 13.5, margin: 0 }}>{error}</p>
      )}
    </div>
  );
}
