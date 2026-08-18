/* Inline markdown field. It shows rendered markdown until a double click,
 * or Enter on the focused preview, swaps in a raw-text editor; blur renders
 * it again. Both halves stay mounted and take turns being hidden, so the
 * field keeps its place in the layout across the swap.
 *
 * The preview keeps a default cursor, not a text caret, so it never pretends to
 * be a plain text field; a subtle hover background hints that it is an editable
 * region entered by double click or Enter. Its text stays selectable and
 * copyable.
 *
 * Properties:
 *   - value: Raw markdown text, owned by the caller.
 *   - on_change: Fired on every keystroke with the new raw text.
 *   - on_commit: Fired on blur, once the preview is back, mirroring how a
 *     plain textarea reports a finished edit.
 *   - placeholder: Stands in for the text while it is empty, in both halves.
 *   - rows: How many lines tall the editor opens.
 *   - min_height: Floor under both halves, in pixels, so a short field does
 *     not shrink as it swaps.
 *   - className: Extra class for the host element.
 *
 * While editing, a small formatting toolbar rides above the textarea with
 * bold, italic, bulleted list and link actions. Its buttons prevent the
 * default mouse down so pressing one does not blur the textarea (a blur
 * commits and swaps back to preview); each runs a pure transform from
 * md-edit.ts through execCommand so native undo and the caret survive.
 * Ctrl/Cmd+B, Ctrl/Cmd+I and Ctrl/Cmd+K run the same bold, italic and
 * link actions for power users.
 *
 * State:
 *   - editing: Which half is showing, the editor or the preview.
 *   - textarea and preview: The two halves, in refs so focus can hop
 *     between them and the editor can be grown to fit its text.
 */
import {
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { marked } from "marked";
import DOMPurify from "dompurify";
import { useTranslation } from "react-i18next";
import { icon } from "./icon";
import { make_link, prefix_lines, wrap, type Edit } from "./md-edit";
import "./md-input.css";

marked.use({
  breaks: true,
  tokenizer: {
    del() {
      return undefined; /* ignore ~ (strikethrough) */
    },
  },
});

function render_markdown(raw: string): string {
  return DOMPurify.sanitize(marked.parse(raw, { async: false }));
}

export function MdInput(props: {
  value: string;
  on_change: (value: string) => void;
  on_commit?: () => void;
  placeholder?: string;
  rows?: number;
  min_height?: number;
  className?: string;
}) {
  const { t } = useTranslation();
  const [editing, set_editing] = useState(false);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const preview = useRef<HTMLDivElement>(null);
  const placeholder = props.placeholder ?? "";

  /* Grow the textarea to fit its content whenever it is the visible half. */
  function resize(): void {
    const tarea = textarea.current;
    if (tarea === null)
      return;
    tarea.style.height = "auto";
    tarea.style.height = `${tarea.scrollHeight}px`;
  }

  /* When edit mode turns on, reveal the textarea, size it and take focus. */
  useLayoutEffect(() => {
    if (!editing)
      return;
    resize();
    textarea.current?.focus();
  }, [editing]);

  function enter_edit(): void {
    set_editing(true);
  }

  /* Run a pure selection transform against the live textarea. The range
   * replacement goes through execCommand so it joins the native undo stack,
   * then the reported selection is restored on top of the fresh text.
   */
  function apply(
    action: (value: string, sel_start: number, sel_end: number) => Edit,
  ): void {
    const ta = textarea.current;
    if (ta === null)
      return;
    const edit = action(ta.value, ta.selectionStart, ta.selectionEnd);
    ta.focus();
    ta.setSelectionRange(edit.start, edit.end);
    document.execCommand?.("insertText", false, edit.insert);
    ta.setSelectionRange(edit.sel_start, edit.sel_end);
  }

  function on_blur(): void {
    set_editing(false);
    props.on_commit?.();
  }

  function on_editor_keydown(
    event: ReactKeyboardEvent<HTMLTextAreaElement>,
  ): void {
    if (event.key === "Escape") {
      event.preventDefault();
      textarea.current?.blur(); /* fires blur -> preview */
      preview.current?.focus(); /* land back on the rendered text */
    } else if (event.key === "Tab") {
      event.preventDefault(); /* don't move focus */
      document.execCommand?.("insertText", false, "  ");
    } else if (event.ctrlKey || event.metaKey) {
      const key = event.key.toLowerCase();
      if (key === "b") {
        event.preventDefault();
        apply((v, s, e) => wrap(v, s, e, "**"));
      } else if (key === "i") {
        event.preventDefault();
        apply((v, s, e) => wrap(v, s, e, "*"));
      } else if (key === "k") {
        event.preventDefault();
        apply(make_link);
      }
    }
  }

  function on_preview_keydown(
    event: ReactKeyboardEvent<HTMLDivElement>,
  ): void {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault(); /* don't let the newline reach the editor */
      enter_edit();
    }
  }

  const size: CSSProperties | undefined = props.min_height
    ? { minHeight: `${props.min_height}px` }
    : undefined;

  const html = props.value.trim()
    ? { __html: render_markdown(props.value) }
    : {
        __html:
          `<span class="md-placeholder">${placeholder}</span>`,
      };

  const host_class = props.className
    ? `md-input ${props.className}`
    : "md-input";

  return (
    <div className={host_class}>
      {editing && (
        <div className="md-toolbar">
          <button
            type="button"
            className="icon-btn"
            title={t("md.bold")}
            aria-label={t("md.bold")}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => apply((v, s, e) => wrap(v, s, e, "**"))}
          >
            {icon("bold", 16)}
          </button>
          <button
            type="button"
            className="icon-btn"
            title={t("md.italic")}
            aria-label={t("md.italic")}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => apply((v, s, e) => wrap(v, s, e, "*"))}
          >
            {icon("italic", 16)}
          </button>
          <button
            type="button"
            className="icon-btn"
            title={t("md.list")}
            aria-label={t("md.list")}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => apply((v, s, e) => prefix_lines(v, s, e, "- "))}
          >
            {icon("list", 16)}
          </button>
          <button
            type="button"
            className="icon-btn"
            title={t("md.link")}
            aria-label={t("md.link")}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => apply(make_link)}
          >
            {icon("link", 16)}
          </button>
        </div>
      )}
      <textarea
        ref={textarea}
        className="md-editor"
        hidden={!editing}
        rows={props.rows ?? 1}
        style={size}
        placeholder={placeholder}
        value={props.value}
        onInput={() => resize()}
        onChange={(event) => props.on_change(event.target.value)}
        onKeyDown={on_editor_keydown}
        onBlur={on_blur}
      />
      <div
        ref={preview}
        className="md-preview"
        hidden={editing}
        tabIndex={0}
        role="textbox"
        aria-label={placeholder}
        style={size}
        onDoubleClick={enter_edit}
        onKeyDown={on_preview_keydown}
        dangerouslySetInnerHTML={html}
      />
    </div>
  );
}
