import { useEffect, useState } from "react";
import { ApiError, getSource, type SourceView } from "../api/client";

interface Props {
  chunkId: string;
  onClose: () => void;
}

export function SourcePanel({ chunkId, onClose }: Props) {
  const [source, setSource] = useState<SourceView | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setSource(null);
    setError(null);
    getSource(chunkId)
      .then((view) => active && setSource(view))
      .catch((caught: unknown) => {
        if (!active) return;
        setError(caught instanceof ApiError && caught.status === 404 ? "This passage isn't available." : "The passage could not be loaded.");
      });
    return () => {
      active = false;
    };
  }, [chunkId]);

  return (
    <section className="source" aria-label="Source passage">
      <div className="source-head">
        <h2>{source ? source.chunk.citation : "Source passage"}</h2>
        <button type="button" onClick={onClose}>
          Close
        </button>
      </div>
      {error && <p role="alert">{error}</p>}
      {source && (
        <>
          {source.quarantined && (
            <p className="quarantine-note">
              Quarantined by {source.quarantine_layer} checks ({source.detectors.join(", ")}). Never used in answers.
            </p>
          )}
          <p className="source-meta">
            {source.chunk.jurisdiction.replaceAll("_", " ")}, {source.chunk.doc_type.replaceAll("_", " ")}.{" "}
            Official source: <span className="url">{source.chunk.url}</span>
          </p>
          <p className="source-text">{source.chunk.text}</p>
        </>
      )}
    </section>
  );
}
