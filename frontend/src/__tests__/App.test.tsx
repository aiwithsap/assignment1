import { render, screen } from "@testing-library/react";
import { App } from "../App";

describe("App shell", () => {
  it("renders the title and the not-legal-advice notice", () => {
    render(<App />);
    expect(screen.getByRole("heading", { name: "Legislation Q&A" })).toBeTruthy();
    expect(screen.getByText(/Not legal advice/)).toBeTruthy();
  });
});
