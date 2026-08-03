import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MdInput } from "./md-input";

/* Small host so the field stays controlled, the way the cards drive it. */
function Host(props: {
  initial?: string;
  on_commit?: () => void;
}) {
  const [value, set_value] = useState(props.initial ?? "");
  return (
    <MdInput
      placeholder="Notes"
      value={value}
      on_change={set_value}
      on_commit={props.on_commit}
    />
  );
}

describe("md-input", () => {
  it("renders markdown in the preview", () => {
    const { container } = render(<Host initial="**bold**" />);
    expect(container.querySelector(".md-preview strong")).toBeInTheDocument();
  });

  it("shows the placeholder while empty", () => {
    const { container } = render(<Host />);
    expect(
      container.querySelector(".md-placeholder"),
    ).toHaveTextContent("Notes");
  });

  it("keeps the raw text available for the caller", () => {
    render(<Host initial="A to B" />);
    expect(screen.getByDisplayValue("A to B")).toBeInTheDocument();
  });

  it("swaps to the editor on double-click", async () => {
    const user = userEvent.setup();
    const { container } = render(<Host initial="hi" />);
    const editor = container.querySelector(".md-editor") as HTMLTextAreaElement;
    expect(editor.hidden).toBe(true);
    await user.dblClick(container.querySelector(".md-preview")!);
    expect(editor.hidden).toBe(false);
    expect(editor).toHaveFocus();
  });

  it("enters the editor from the keyboard", async () => {
    const user = userEvent.setup();
    const { container } = render(<Host />);
    const preview = container.querySelector(".md-preview") as HTMLDivElement;
    preview.focus();
    await user.keyboard("{Enter}");
    expect((container.querySelector(".md-editor") as HTMLTextAreaElement).hidden)
      .toBe(false);
  });

  it("commits and re-renders the preview on blur", async () => {
    const user = userEvent.setup();
    const on_commit = vi.fn();
    const { container } = render(<Host on_commit={on_commit} />);
    await user.dblClick(container.querySelector(".md-preview")!);
    await user.keyboard("# Title");
    fireEvent.blur(container.querySelector(".md-editor")!);
    expect(on_commit).toHaveBeenCalledOnce();
    expect(container.querySelector(".md-preview h1")).toHaveTextContent("Title");
  });
});
