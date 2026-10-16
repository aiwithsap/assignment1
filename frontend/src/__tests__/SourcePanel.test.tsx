import { render, screen, waitFor } from "@testing-library/react";
import { SourcePanel } from "../components/SourcePanel";
import { HOSTILE, jsonResponse } from "./fixtures";

afterEach(() => vi.unstubAllGlobals());

const chunk = {
  chunk_id: "adv_0123456789ab",
  version_id: "v1",
  citation: "Fees Determination 2020 (Cth)",
  jurisdiction: "commonwealth",
  doc_type: "secondary_legislation",
  url: "https://www.legislation.gov.au/x",
  text: HOSTILE,
};

describe("SourcePanel", () => {
  it("shows a quarantined passage as inert text with its quarantine reason", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(200, { chunk, quarantined: true, quarantine_layer: "provenance", detectors: ["PROV"] }),
      ),
    );
    const { container } = render(<SourcePanel chunkId={chunk.chunk_id} onClose={() => undefined} />);
    await waitFor(() => expect(screen.getByText(/Quarantined by provenance checks/)).toBeTruthy());
    expect(screen.getByText(HOSTILE)).toBeTruthy();
    expect(container.querySelector("script, img")).toBeNull();
  });

  it("reports an unavailable passage", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse(404, { detail: "unknown source" })));
    render(<SourcePanel chunkId="c_ffffffffffff" onClose={() => undefined} />);
    await waitFor(() => expect(screen.getByRole("alert").textContent).toMatch(/isn't available/));
  });
});
