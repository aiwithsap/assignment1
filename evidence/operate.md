# Operating the service

## Run

```bash
uv sync
uv run legisqa ask "What are the assay limits for the content of active ingredients or components in tablets and capsules?"
uv run legisqa serve                 # API and UI on http://127.0.0.1:8000, OpenAPI docs at /docs
uv run legisqa serve --profile demo  # also loads the attack overlay and the security endpoints
```

Build the UI once (Node 20 or later): `cd frontend && npm ci && npm run build`.

## Configuration

- Environment variables prefixed `LEGISQA_`; every setting and its default is listed in `.env.example`.
- Profiles: `prod` (default; no attack overlay, no security endpoints), `demo`, `eval`.
- Settings are validated once at startup and are immutable. **Changing a setting requires a restart**;
  there is no hot reload.
- The answerability gate (`LEGISQA_GATE_MIN_STRENGTH=0.88`, `LEGISQA_GATE_MIN_MARGIN=0.15`) was chosen on
  the dev split. Changing it changes the safety/coverage trade-off: re-run `legisqa eval dev` and the
  acceptance targets before deploying a new value.

## Secrets

None. The service holds no credentials and makes no outbound calls. In production, credentials for
authentication would be injected from the platform's secrets manager at runtime, never baked into the
image or the repository. `verify.py` scans everything committable for credential-shaped strings.

## Logs, audit and status

| Signal | Where | Contents |
|---|---|---|
| Application log | stdout, JSON lines | Stage (`guard`, `retrieve`, `answer`, `validate`), `request_id`, gate strength and margin, outcome. Never question text |
| Answer audit | `var/audit/answers.jsonl` | Request id, time, question length and fingerprint, outcome, reason or rejection code, corpus version, retrieved ids and scores, cited ids, security event ids, latency |
| Security events | `var/audit/security.jsonl`; `GET /v1/security-events` (demo/eval) | Detector, severity, rule, offsets, passage or request id, action taken; text only for corpus findings, truncated to 80 characters |
| Liveness | `GET /healthz` | Always 200 while the process runs |
| Readiness | `GET /readyz` | 200 only when the corpus loaded and verified and the audit log is writable; 503 with reasons otherwise; a warning if more than 8 genuine passages are quarantined |

Every response carries `X-Request-ID`; a caller-supplied id is echoed back.

## Failure modes

| Failure | Detection | Behaviour | Operator action |
|---|---|---|---|
| Corpus file missing or altered | Manifest hash mismatch at startup | Process runs unready: `/readyz` 503, `/v1/answers` 503 `not_ready`, CLI exit 3 | Restore the published snapshot; investigate the change |
| Manifest from an incompatible build | Schema version check | Unready, as above | Deploy a matching code and corpus pair |
| Poisoned passage in a release | L1 or L2 at load; security events | Passage quarantined; never retrievable | Review the quarantine list; a jump in count blocks promotion |
| Audit log not writable | Write error | Response withheld, 503 `audit_unavailable` | Fix storage; answers resume without restart |
| PII, markup or hidden characters in a question | L3 guard | 422 with code; text not logged | None; repeated attempts are visible in the audit |
| Injection wording in a question | L3 detectors | Answered normally; security event logged | Review for abuse patterns |
| Weak or ambiguous evidence | Gate | Abstain `low_evidence` | None; review abstain rate trends |
| Citation fails verification | Validator | Abstain `ungrounded` | Investigate: should not happen with the extractive answerer |
| Unsafe content in an answer | L5 output guard | Abstain `unsafe_output` plus security event | Find the passage; quarantine or fix the corpus |
| Unexpected exception | Handler | 500 envelope with request id; stack trace in log | Use the request id to find the trace |

## Rollback and degrade

- Code and corpus are versioned separately but deployed as a **compatible pair**; the manifest's schema
  version is checked at startup, so an incompatible pair stays unready instead of half-working.
- Roll back by redeploying the previous image tag and corpus snapshot. A suspicious corpus release can be
  rolled back without touching code.
- The service degrades to abstaining, never to guessing: a tighter gate is a safe emergency setting
  (restart required).

## Local to cloud

1. **Pull request:** `uv run python scripts/verify.py --require-frontend` (format, lint, types, tests with
   85% coverage floor, corpus integrity, evaluation and security gates, UI checks, hygiene), plus
   dependency audit, secret scanning, SBOM, container build and image scan. Implemented locally and in
   GitHub Actions today: `verify.py`. The rest is the proposed pipeline.
2. **Merge:** sign the image; publish the corpus through its own pipeline (fetch from the authoritative
   source, rebuild, provenance and scan, evaluation gates, human review of the quarantine list).
3. **Staging:** deploy the pair; run the evaluation and security suite against the running service.
4. **Production:** change approval recording the risk owner; canary with alerts on abstain rate,
   `unsafe_output` rate, quarantine count and p95 latency; automatic rollback to the last good pair.
