// Typed client for the answers API. Types are generated from the service's OpenAPI schema
// (npm run gen:types), so the UI and API cannot drift apart silently.
import type { components } from "./schema";

export type AnswerResponse = components["schemas"]["AnswerResponse"];
export type ErrorEnvelope = components["schemas"]["ErrorEnvelope"];
export type SourceView = components["schemas"]["SourceView"];
export type SecurityEvent = components["schemas"]["SecurityEvent"];
export type ReadinessView = components["schemas"]["ReadinessView"];
export type Jurisdiction = NonNullable<components["schemas"]["AskRequest"]["jurisdiction"]>;

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly envelope: ErrorEnvelope | null,
  ) {
    super(envelope?.message ?? `Request failed with status ${status}`);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (response.ok) {
    return (await response.json()) as T;
  }
  let envelope: ErrorEnvelope | null = null;
  try {
    const body: unknown = await response.json();
    if (body !== null && typeof body === "object" && "outcome" in body) {
      envelope = body as ErrorEnvelope;
    }
  } catch {
    envelope = null;
  }
  throw new ApiError(response.status, envelope);
}

export function ask(question: string, jurisdiction: Jurisdiction | null): Promise<AnswerResponse> {
  return request<AnswerResponse>("/v1/answers", {
    method: "POST",
    body: JSON.stringify({ question, jurisdiction }),
  });
}

export function getSource(chunkId: string): Promise<SourceView> {
  return request<SourceView>(`/v1/sources/${encodeURIComponent(chunkId)}`);
}

/** Security events exist only in the demo and eval profiles; null means not available. */
export async function getSecurityEvents(): Promise<SecurityEvent[] | null> {
  try {
    return await request<SecurityEvent[]>("/v1/security-events");
  } catch (error) {
    if (error instanceof ApiError && (error.status === 404 || error.status === 405)) {
      return null;
    }
    throw error;
  }
}

export function getReadiness(): Promise<ReadinessView> {
  return request<ReadinessView>("/readyz").catch((error: unknown) => {
    // /readyz answers 503 with a ReadinessView body when the service is unready.
    if (error instanceof ApiError) {
      throw error;
    }
    throw new ApiError(0, null);
  });
}
