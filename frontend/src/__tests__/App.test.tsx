import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { App } from "../App";
import { REJECTED, answered, jsonResponse } from "./fixtures";

function mockFetch(routes: Record<string, () => Response>) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = typeof input === "string" ? input : input.toString();
    const handler = Object.entries(routes).find(([path]) => url.startsWith(path))?.[1];
    return handler ? handler() : jsonResponse(404, { detail: "not found" });
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => vi.unstubAllGlobals());

const READY = {
  ready: true,
  reasons: [],
  warnings: [],
  corpus_version: "c-test",
  profile: "prod",
  clean_chunks: 426,
  quarantined_chunks: 0,
};

async function askQuestion(text: string) {
  fireEvent.change(screen.getByLabelText("Your question about Australian legislation"), {
    target: { value: text },
  });
  fireEvent.click(screen.getByRole("button", { name: "Find evidence" }));
}

describe("App", () => {
  it("renders the title and the not-legal-advice notice", () => {
    mockFetch({ "/readyz": () => jsonResponse(200, READY) });
    render(<App />);
    expect(screen.getByRole("heading", { name: "Legislation Q&A" })).toBeTruthy();
    expect(screen.getByText(/Not legal advice/)).toBeTruthy();
  });

  it("asks a question and shows the excerpt", async () => {
    const quote = "A licence holder must pay the annual licence fee before 30 June each year.";
    mockFetch({
      "/readyz": () => jsonResponse(200, READY),
      "/v1/answers": () => jsonResponse(200, answered(quote)),
    });
    render(<App />);
    await askQuestion("When is the licence fee due?");
    await waitFor(() => expect(screen.getByText(quote)).toBeTruthy());
    expect(screen.getByText(/Ready: corpus c-test, 426 passages/)).toBeTruthy();
  });

  it("shows the error envelope message and request id on rejection", async () => {
    mockFetch({
      "/readyz": () => jsonResponse(200, READY),
      "/v1/answers": () => jsonResponse(422, REJECTED),
    });
    render(<App />);
    await askQuestion("my tfn is 123 456 782");
    await waitFor(() => expect(screen.getByRole("alert")).toBeTruthy());
    expect(screen.getByText(REJECTED.message)).toBeTruthy();
    expect(screen.getByText("Request req_rejected")).toBeTruthy();
  });

  it("explains an unreachable service", async () => {
    mockFetch({ "/readyz": () => jsonResponse(503, { ...READY, ready: false }) });
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("network down"); }));
    render(<App />);
    await askQuestion("anything");
    await waitFor(() => expect(screen.getByText(/could not be reached/)).toBeTruthy());
  });

  it("hides the security panel when the profile does not expose it", async () => {
    mockFetch({ "/readyz": () => jsonResponse(200, READY) });
    render(<App />);
    await waitFor(() => expect(screen.queryByLabelText("Security events")).toBeNull());
  });

  it("shows intercepted content in the demo profile", async () => {
    mockFetch({
      "/readyz": () => jsonResponse(200, { ...READY, profile: "demo" }),
      "/v1/security-events": () =>
        jsonResponse(200, [
          {
            event_id: "se_1",
            ts: "2026-10-16T00:00:00Z",
            source: "corpus",
            action: "quarantined",
            detector: "PROV",
            severity: "HIGH",
            rule: "hash_mismatch",
            span: [0, 10],
            chunk_id: "adv_0123456789ab",
            request_id: null,
            matched_text: "<script>x</script>",
            matched_sha256_16: "abcd",
          },
        ]),
    });
    const { container } = render(<App />);
    await waitFor(() => expect(screen.getByText("Intercepted content")).toBeTruthy());
    expect(screen.getByText(/1 passages quarantined/)).toBeTruthy();
    expect(container.querySelector("script")).toBeNull();
  });
});
