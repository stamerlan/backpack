import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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

  describe("formatting toolbar", () => {
    /* jsdom leaves execCommand a no-op, so stand in a version that runs the
     * insertText the component asks for: splice the given text over the
     * current selection and fire the input event React's onChange listens
     * for, driving it through the same value tracker a real browser would.
     */
    let original_exec: typeof document.execCommand;

    beforeEach(() => {
      original_exec = document.execCommand;
      document.execCommand = ((
        _command: string, _ui?: boolean, text?: string,
      ): boolean => {
        const ta = document.activeElement as HTMLTextAreaElement | null;
        if (ta === null)
          return false;
        const start = ta.selectionStart ?? 0;
        const end = ta.selectionEnd ?? 0;
        const next =
          ta.value.slice(0, start) + (text ?? "") + ta.value.slice(end);
        const setter = Object.getOwnPropertyDescriptor(
          window.HTMLTextAreaElement.prototype, "value",
        )?.set;
        setter?.call(ta, next);
        ta.dispatchEvent(new Event("input", { bubbles: true }));
        return true;
      }) as typeof document.execCommand;
    });

    afterEach(() => {
      document.execCommand = original_exec;
    });

    it("hides the toolbar in preview and shows it while editing", async () => {
      const user = userEvent.setup();
      const { container } = render(<Host initial="hi" />);
      expect(container.querySelector(".md-toolbar")).toBeNull();
      await user.dblClick(container.querySelector(".md-preview")!);
      expect(container.querySelector(".md-toolbar")).not.toBeNull();
    });

    it("wraps the current selection when bold is clicked", async () => {
      const user = userEvent.setup();
      const { container } = render(<Host initial="hi" />);
      const editor = container.querySelector(
        ".md-editor",
      ) as HTMLTextAreaElement;
      await user.dblClick(container.querySelector(".md-preview")!);
      editor.setSelectionRange(0, editor.value.length);
      await user.click(screen.getByRole("button", { name: "Bold" }));
      expect(editor.value).toBe("**hi**");
    });

    it("keeps focus and does not commit when a button is clicked", async () => {
      const user = userEvent.setup();
      const on_commit = vi.fn();
      const { container } = render(<Host initial="hi" on_commit={on_commit} />);
      const editor = container.querySelector(
        ".md-editor",
      ) as HTMLTextAreaElement;
      await user.dblClick(container.querySelector(".md-preview")!);
      await user.click(screen.getByRole("button", { name: "Italic" }));
      expect(on_commit).not.toHaveBeenCalled();
      expect(editor.hidden).toBe(false);
      expect(editor).toHaveFocus();
    });
  });
});
