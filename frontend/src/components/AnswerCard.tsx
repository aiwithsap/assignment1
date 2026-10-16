import type { AnswerResponse } from "../api/client";
import { CitationList } from "./CitationList";

const ABSTAIN_MESSAGES: Record<string, string> = {
  low_evidence:
    "The corpus doesn't contain strong enough evidence to answer this. Try naming the Act or instrument, or rephrasing.",
  ungrounded: "An excerpt was found but its citation could not be verified, so it was withheld.",
  unsafe_output:
    "The best matching passage contained unsafe content (links, markup or instructions), so it was withheld and logged.",
};

interface Props {
  response: AnswerResponse;
  onOpenSource: (chunkId: string) => void;
}

export function AnswerCard({ response, onOpenSource }: Props) {
  const { result } = response;
  const top = response.retrieved[0];
  if (result.status === "abstained") {
    const reason = result.abstain_reason ?? "low_evidence";
    return (
      <section className="result abstained" aria-label="Result">
        <p className="status">No answer</p>
        <p>{ABSTAIN_MESSAGES[reason] ?? reason}</p>
        <Footer response={response} />
      </section>
    );
  }
  return (
    <section className="result answered" aria-label="Result">
      <p className="status">Evidence found</p>
      <CitationList
        citations={result.citations}
        matchedTerms={top?.top_terms ?? []}
        onOpenSource={onOpenSource}
      />
      <Footer response={response} />
    </section>
  );
}

function Footer({ response }: { response: AnswerResponse }) {
  return (
    <p className="footer">
      Request {response.request_id}, corpus {response.corpus_version}, {response.latency_ms.toFixed(1)} ms.{" "}
      {response.notice}
    </p>
  );
}
