import { useState, type FormEvent } from "react";
import type { Jurisdiction } from "../api/client";

export const MAX_QUESTION_CHARS = 500;

const JURISDICTIONS: { value: Jurisdiction; label: string }[] = [
  { value: "commonwealth", label: "Commonwealth" },
  { value: "new_south_wales", label: "New South Wales" },
  { value: "queensland", label: "Queensland" },
  { value: "western_australia", label: "Western Australia" },
  { value: "south_australia", label: "South Australia" },
  { value: "tasmania", label: "Tasmania" },
  { value: "norfolk_island", label: "Norfolk Island" },
];

interface Props {
  busy: boolean;
  onAsk: (question: string, jurisdiction: Jurisdiction | null) => void;
}

export function AskForm({ busy, onAsk }: Props) {
  const [question, setQuestion] = useState("");
  const [jurisdiction, setJurisdiction] = useState<Jurisdiction | "">("");
  const remaining = MAX_QUESTION_CHARS - question.length;

  function submit(event: FormEvent) {
    event.preventDefault();
    if (question.trim().length > 0 && remaining >= 0) {
      onAsk(question, jurisdiction === "" ? null : jurisdiction);
    }
  }

  return (
    <form className="ask" onSubmit={submit}>
      <label htmlFor="question">Your question about Australian legislation</label>
      <textarea
        id="question"
        rows={3}
        value={question}
        maxLength={MAX_QUESTION_CHARS}
        placeholder="For example: What are the assay limits for active ingredients in tablets and capsules?"
        onChange={(event) => setQuestion(event.target.value)}
      />
      <div className="ask-row">
        <label className="inline" htmlFor="jurisdiction">
          Jurisdiction
          <select
            id="jurisdiction"
            value={jurisdiction}
            onChange={(event) => setJurisdiction(event.target.value as Jurisdiction | "")}
          >
            <option value="">All</option>
            {JURISDICTIONS.map((j) => (
              <option key={j.value} value={j.value}>
                {j.label}
              </option>
            ))}
          </select>
        </label>
        <span className="hint" aria-live="polite">
          {remaining} characters left
        </span>
        <button type="submit" disabled={busy || question.trim().length === 0}>
          {busy ? "Searching" : "Find evidence"}
        </button>
      </div>
      <p className="hint">Plain text only. Don't include personal details such as a tax file number.</p>
    </form>
  );
}
