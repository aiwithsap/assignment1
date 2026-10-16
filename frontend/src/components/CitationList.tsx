import type { AnswerResponse } from "../api/client";

type Citation = AnswerResponse["result"]["citations"][number];

interface Props {
  citations: Citation[];
  matchedTerms: string[];
  onOpenSource: (chunkId: string) => void;
}

// Each excerpt is laid out like a statute page: the citation sits in the margin as a side note,
// the quoted text in the body. Every string is rendered as text, never as HTML.
export function CitationList({ citations, matchedTerms, onOpenSource }: Props) {
  return (
    <ol className="citations">
      {citations.map((citation) => (
        <li key={citation.chunk_id} className="statute">
          <aside className="margin-note">
            <span className="verified">Quote verified against source</span>
            <button type="button" className="link" onClick={() => onOpenSource(citation.chunk_id)}>
              View full passage
            </button>
            {matchedTerms.length > 0 && (
              <span className="terms">Matched on {matchedTerms.join(", ")}</span>
            )}
          </aside>
          <blockquote className="excerpt">{citation.quote}</blockquote>
        </li>
      ))}
    </ol>
  );
}
