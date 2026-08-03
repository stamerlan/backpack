import {
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { marked } from "marked";
import DOMPurify from "dompurify";
import "./md-input.css";

/* Inline markdown field. Shows rendered markdown; on focus it swaps to a
 * raw-text editor, and on blur it re-renders.
 *
 * value: Raw markdown text, owned by the caller.
 * on_change: Fired on every keystroke with the new raw text.
 * on_commit: Fired on blur, once the preview is back, mirroring how a plain
 *  textarea reports a finished edit.
 */
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
  const [editing, set_editing] = useState(false);
  const textarea = useRef<HTMLTextAreaElement>(null);
  const preview = useRef<HTMLDivElement>(null);
  const placeholder = props.placeholder ?? "";

  /* Grow the textarea to fit its content whenever it is the visible half. */
  function resize(): void {
    const t = textarea.current;
    if (t === null)
      return;
    t.style.height = "auto";
    t.style.height = `${t.scrollHeight}px`;
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
