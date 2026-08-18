/* Pure selection transforms for the inline markdown editor. Each helper takes
 * the raw text and the current selection (value, sel_start, sel_end) and
 * returns a range-based edit, with no reference to the DOM. The caller replaces
 * value[start..end] with insert, then restores the selection to
 * [sel_start, sel_end]; that split keeps the functions unit-testable while the
 * component drives execCommand and setSelectionRange.
 *
 * The returned selection is expressed in the coordinates of the edited text, so
 * the same numbers feed straight into setSelectionRange after the insert lands.
 */

/* A single range replacement plus the selection to restore afterwards.
 *   - start/end: The half-open range in the original value to replace.
 *   - insert: The text put in that range.
 *   - sel_start/sel_end: Where the selection sits once the insert has landed.
 */
export interface Edit {
  start: number;
  end: number;
  insert: string;
  sel_start: number;
  sel_end: number;
}

/* Placeholder dropped into the URL slot of a fresh link, then left selected. */
const URL_PLACEHOLDER = "url";

/* Wrap the selection in marker on both sides, e.g. "**" for bold or "*" for
 * italic. An empty selection inserts the pair and drops the caret between the
 * markers; a real selection stays selected between them.
 */
export function wrap(
  value: string, sel_start: number, sel_end: number, marker: string
): Edit {
  const selected = value.slice(sel_start, sel_end);
  return {
    start: sel_start,
    end: sel_end,
    insert: `${marker}${selected}${marker}`,
    sel_start: sel_start + marker.length,
    sel_end: sel_end + marker.length,
  };
}

/* Prepend prefix, e.g. "- ", to every line the selection touches, from the
 * start of the first line to the end of the last. The selection is shifted to
 * stay over the same text now that each line carries its prefix.
 */
export function prefix_lines(
  value: string, sel_start: number, sel_end: number, prefix: string
): Edit {
  const block_start = value.lastIndexOf("\n", sel_start - 1) + 1;
  const newline = value.indexOf("\n", sel_end);
  const block_end = newline === -1 ? value.length : newline;
  const lines = value.slice(block_start, block_end).split("\n");
  const insert = lines.map((line) => `${prefix}${line}`).join("\n");
  return {
    start: block_start,
    end: block_end,
    insert,
    sel_start: sel_start + prefix.length,
    sel_end: sel_end + prefix.length * lines.length
  };
}

/* Turn the selection into a markdown link, [text](url), leaving the "url"
 * placeholder selected so it can be typed over. An empty selection yields an
 * empty link text, [](url).
 */
export function make_link(
  value: string,sel_start: number,sel_end: number
): Edit {
  const text = value.slice(sel_start, sel_end);
  const url_at = sel_start + text.length + 3; /* past "[text](" */
  return {
    start: sel_start,
    end: sel_end,
    insert: `[${text}](${URL_PLACEHOLDER})`,
    sel_start: url_at,
    sel_end: url_at + URL_PLACEHOLDER.length
  };
}
