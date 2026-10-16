import type { AnswerResponse, ErrorEnvelope } from "../api/client";

export const HOSTILE = `Payload <script>window.pwned = true</script><img src=x onerror="window.pwned = true"> end.`;

export function answered(quote: string): AnswerResponse {
  return {
    request_id: "req_test",
    outcome: "answered",
    corpus_version: "c-test",
    result: {
      status: "answered",
      answer: quote,
      citations: [{ chunk_id: "c_0123456789ab", quote }],
      abstain_reason: null,
    },
    retrieved: [{ chunk_id: "c_0123456789ab", score: 3.2, top_terms: ["licence", "fee"] }],
    security_event_ids: [],
    latency_ms: 1.4,
    notice: "Evidence excerpts from public legislation, provided for research. Not legal advice.",
  };
}

export function abstained(reason: "low_evidence" | "ungrounded" | "unsafe_output"): AnswerResponse {
  return {
    ...answered("x".repeat(30)),
    outcome: "abstained",
    result: { status: "abstained", answer: null, citations: [], abstain_reason: reason },
  };
}

export const REJECTED: ErrorEnvelope = {
  request_id: "req_rejected",
  outcome: "rejected",
  code: "pii_detected",
  message: "The question appears to contain personal information. Please remove it.",
};

export function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
