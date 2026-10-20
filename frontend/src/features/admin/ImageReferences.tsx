import { Button } from "@heroui/react";
import { useState } from "react";
import { apiFetch } from "../../api/client";

import type { ImageReference } from "../../api/admin";

export function ImageReferences({
  value,
  onChange,
  onBusyChange,
}: {
  value: ImageReference[];
  onChange: (next: ImageReference[]) => void;
  onBusyChange: (busy: boolean) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <fieldset className="image-references">
      <legend>Reference images</legend>
      <p className="text-sm text-muted">
        Upload character sheets and scene references for this adventure. All
        saved references accompany every illustration request. Up to 4 images, 8
        MB each; PNG, JPEG or WebP. Choose an image model that accepts reference
        images.
      </p>
      <div className="reference-grid">
        {value.map((reference) => (
          <article key={reference.id} className="reference-card">
            <img src={reference.url} alt={reference.name} />
            <div>
              <strong>{reference.name}</strong>
              <small>
                {reference.kind === "character"
                  ? "Character sheet"
                  : "Scene reference"}
              </small>
            </div>
            <Button
              type="button"
              size="sm"
              variant="danger-soft"
              isDisabled={busy}
              onPress={() =>
                onChange(value.filter((r) => r.id !== reference.id))
              }
              aria-label={`Remove ${reference.name}`}
            >
              Remove
            </Button>
          </article>
        ))}
      </div>
      <div className="reference-uploads">
        {(["character", "scene"] as const).map((kind) => (
          <label key={kind}>
            {kind === "character"
              ? "Upload character sheet"
              : "Upload scene reference"}
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp"
              disabled={busy || value.length >= 4}
              onChange={async (event) => {
                const file = event.target.files?.[0];
                event.target.value = "";
                if (!file) return;
                setError("");
                if (file.size > 8 * 1024 * 1024) {
                  setError("Choose an image up to 8 MB.");
                  return;
                }
                setBusy(true);
                onBusyChange(true);
                try {
                  const payload = new FormData();
                  payload.append("image", file);
                  payload.append("kind", kind);
                  payload.append("name", file.name);
                  const uploaded = await apiFetch<ImageReference>(
                    "/api/v1/admin/image-references",
                    { payload },
                  );
                  onChange([...value, uploaded]);
                } catch (failure) {
                  setError(
                    failure instanceof Error
                      ? failure.message
                      : "Upload failed. Please try again.",
                  );
                } finally {
                  setBusy(false);
                  onBusyChange(false);
                }
              }}
            />
          </label>
        ))}
      </div>
      {busy && <p role="status">Uploading reference image…</p>}
      {error && <p role="alert">{error}</p>}
    </fieldset>
  );
}
