import { fireEvent, render, screen } from "@testing-library/react";
import { AnswerCard } from "../components/AnswerCard";
import { HOSTILE, abstained, answered } from "./fixtures";

describe("AnswerCard", () => {
  it("shows a verified excerpt with its margin note", () => {
    const quote = "A licence holder must pay the annual licence fee before 30 June each year.";
    const onOpen = vi.fn();
    render(<AnswerCard response={answered(quote)} onOpenSource={onOpen} />);
    expect(screen.getByText("Evidence found")).toBeTruthy();
    expect(screen.getByText(quote)).toBeTruthy();
    expect(screen.getByText("Quote verified against source")).toBeTruthy();
    expect(screen.getByText("Matched on licence, fee")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "View full passage" }));
    expect(onOpen).toHaveBeenCalledWith("c_0123456789ab");
  });

  it.each([
    ["low_evidence", /doesn't contain strong enough evidence/],
    ["ungrounded", /could not be verified/],
    ["unsafe_output", /unsafe content/],
  ] as const)("explains the %s abstention", (reason, message) => {
    render(<AnswerCard response={abstained(reason)} onOpenSource={() => undefined} />);
    expect(screen.getByText("No answer")).toBeTruthy();
    expect(screen.getByText(message)).toBeTruthy();
  });

  it("renders hostile text inert: no script or image element is created", () => {
    const { container } = render(<AnswerCard response={answered(HOSTILE)} onOpenSource={() => undefined} />);
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText(HOSTILE)).toBeTruthy();
    expect((window as unknown as { pwned?: boolean }).pwned).toBeUndefined();
  });
});
