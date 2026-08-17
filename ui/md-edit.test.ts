import { describe, expect, it } from "vitest";
import { make_link, prefix_lines, wrap, type Edit } from "./md-edit";

/* Apply an edit the way the component does: splice insert into the range, then
 * report where the selection lands, so a test reads the finished text and caret
 * together.
 */
function apply(value: string, edit: Edit): { text: string; sel: string } {
  const text = value.slice(0, edit.start) + edit.insert + value.slice(edit.end);
  return { text, sel: text.slice(edit.sel_start, edit.sel_end) };
}

describe("wrap", () => {
  it("wraps a selection and keeps it selected", () => {
    const value = "make bold now";
    const { text, sel } = apply(value, wrap(value, 5, 9, "**"));
    expect(text).toBe("make **bold** now");
    expect(sel).toBe("bold");
  });

  it("inserts the markers and drops the caret between them", () => {
    const value = "empty ";
    const edit = wrap(value, 6, 6, "**");
    const { text } = apply(value, edit);
    expect(text).toBe("empty ****");
    expect(edit.sel_start).toBe(edit.sel_end); /* caret, not a range */
    expect(edit.sel_start).toBe(8); /* between the two "**" */
  });

  it("uses a single marker for italic", () => {
    const value = "go slow";
    const { text, sel } = apply(value, wrap(value, 3, 7, "*"));
    expect(text).toBe("go *slow*");
    expect(sel).toBe("slow");
  });
});

describe("prefix_lines", () => {
  it("prefixes a single line the selection sits on", () => {
    const value = "one";
    const { text, sel } = apply(value, prefix_lines(value, 1, 2, "- "));
    expect(text).toBe("- one");
    expect(sel).toBe("n");
  });

  it("prefixes every line the selection touches", () => {
    const value = "one\ntwo\nthree";
    /* Selection starts in line one and ends in line three. */
    const { text } = apply(value, prefix_lines(value, 1, 10, "- "));
    expect(text).toBe("- one\n- two\n- three");
  });

  it("prefixes from the line start even when the selection is empty", () => {
    const value = "alpha\nbeta";
    const { text } = apply(value, prefix_lines(value, 8, 8, "- "));
    expect(text).toBe("alpha\n- beta");
  });
});

describe("make_link", () => {
  it("wraps the selection as link text and selects the url slot", () => {
    const value = "see docs here";
    const { text, sel } = apply(value, make_link(value, 4, 8));
    expect(text).toBe("see [docs](url) here");
    expect(sel).toBe("url");
  });

  it("makes an empty link and selects the url slot", () => {
    const value = "";
    const { text, sel } = apply(value, make_link(value, 0, 0));
    expect(text).toBe("[](url)");
    expect(sel).toBe("url");
  });
});
