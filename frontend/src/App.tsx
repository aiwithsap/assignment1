import { useEffect, useState } from "react";
import {
  ApiError,
  ask,
  getReadiness,
  type AnswerResponse,
  type Jurisdiction,
  type ReadinessView,
} from "./api/client";
import { AnswerCard } from "./components/AnswerCard";
import { AskForm } from "./components/AskForm";
import { SecurityPanel } from "./components/SecurityPanel";
import { SourcePanel } from "./components/SourcePanel";

interface Failure {
  message: string;
  requestId: string | null;
}

export function App() {
  const [busy, setBusy] = useState(false);
  const [response, setResponse] = useState<AnswerResponse | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [sourceId, setSourceId] = useState<string | null>(null);
  const [readiness, setReadiness] = useState<ReadinessView | null>(null);
  const [asked, setAsked] = useState(0);

  useEffect(() => {
    getReadiness()
      .then(setReadiness)
      .catch(() => setReadiness(null));
  }, []);

  async function onAsk(question: string, jurisdiction: Jurisdiction | null) {
    setBusy(true);
    setFailure(null);
    setSourceId(null);
    try {
      setResponse(await ask(question, jurisdiction));
    } catch (error) {
      setResponse(null);
      if (error instanceof ApiError && error.envelope) {
        setFailure({ message: error.envelope.message, requestId: error.envelope.request_id });
      } else {
        setFailure({ message: "The service could not be reached. Check that it is running.", requestId: null });
      }
    } finally {
      setBusy(false);
      setAsked((n) => n + 1);
    }
  }

  return (
    <main className="app">
      <header>
        <h1>Legislation Q&amp;A</h1>
        <p className="tagline">
          Evidence excerpts from Australian legislation, with verified citations. Not legal advice.
        </p>
        {readiness && (
          <p className="readiness">
            {readiness.ready ? "Ready" : "Not ready"}: corpus {readiness.corpus_version ?? "not loaded"},{" "}
            {readiness.clean_chunks} passages, profile {readiness.profile}.
          </p>
        )}
      </header>
      <AskForm busy={busy} onAsk={onAsk} />
      {failure && (
        <section className="result failed" role="alert">
          <p className="status">Request not answered</p>
          <p>{failure.message}</p>
          {failure.requestId && <p className="footer">Request {failure.requestId}</p>}
        </section>
      )}
      {response && <AnswerCard response={response} onOpenSource={setSourceId} />}
      {sourceId && <SourcePanel chunkId={sourceId} onClose={() => setSourceId(null)} />}
      <SecurityPanel refreshKey={asked} onOpenSource={setSourceId} />
    </main>
  );
}
