import { useEffect, useState } from "react";
import { getSecurityEvents, type SecurityEvent } from "../api/client";

interface Props {
  refreshKey: number;
  onOpenSource: (chunkId: string) => void;
}

// Visible only when the service runs in the demo or eval profile.
export function SecurityPanel({ refreshKey, onOpenSource }: Props) {
  const [events, setEvents] = useState<SecurityEvent[] | null>(null);

  useEffect(() => {
    getSecurityEvents()
      .then(setEvents)
      .catch(() => setEvents(null));
  }, [refreshKey]);

  if (events === null) return null;
  const quarantined = [...new Set(events.filter((e) => e.action === "quarantined").map((e) => e.chunk_id))];
  const requestEvents = events.filter((e) => e.source !== "corpus");

  return (
    <section className="security" aria-label="Security events">
      <h2>Intercepted content</h2>
      <p>
        {quarantined.length} passages quarantined at load; {requestEvents.length} events raised by questions or answers.
      </p>
      <table>
        <thead>
          <tr>
            <th scope="col">Where</th>
            <th scope="col">Detector</th>
            <th scope="col">Rule</th>
            <th scope="col">Action</th>
            <th scope="col">Passage</th>
          </tr>
        </thead>
        <tbody>
          {events.slice(-40).reverse().map((e) => (
            <tr key={e.event_id}>
              <td>{e.source}</td>
              <td>{e.detector}</td>
              <td>{e.rule.replaceAll("_", " ")}</td>
              <td>{e.action}</td>
              <td>
                {e.chunk_id ? (
                  <button type="button" className="link" onClick={() => onOpenSource(e.chunk_id as string)}>
                    {e.chunk_id}
                  </button>
                ) : (
                  "n/a"
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
