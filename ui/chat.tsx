/* One chat: the turn log with the assistant's thinking, replies and cards,
 * and the composer beneath it. The panel keeps every chat mounted and shows
 * one at a time, so the turns and the busy flag are owned by Assist rather
 * than held here.
 *
 * Properties:
 *   - chat_id: Model id of the chat, quoted back to the backend.
 *   - visible: Whether this is the chat the tab strip has selected.
 *   - turns: The conversation so far, oldest first.
 *   - busy: Whether the last turn is still streaming.
 *   - models: Assistant models offered in the composer menu.
 *   - selected_model: Model the next prompt will be sent to.
 *   - on_model_change: Reports a model picked from the composer menu.
 *
 * State:
 *   - prompt: What the user has typed but not yet sent.
 *   - sending: Whether a prompt is on its way to the backend, which the
 *     busy flag only reflects once the backend has answered.
 */
import {
  memo,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import {
  Button,
  CompoundButton,
  Menu,
  MenuButton,
  MenuItem,
  MenuList,
  MenuPopover,
  MenuTrigger,
  mergeClasses,
  Spinner,
  Text,
} from "@fluentui/react-components";
import { useTranslation } from "react-i18next";
import { marked } from "marked";
import DOMPurify from "dompurify";
import api from "./api";
import { icon } from "./icon";
import { ChatCardView, type ChatCardData } from "./card";
import "./chat.css";

marked.use({ breaks: true });

/* A block of rendered markdown. Every chat stays mounted so it keeps its
 * draft and its scroll position, and each streamed token re-renders all of
 * them, so the memo is what stops that from re-parsing and re-sanitizing
 * every block in every chat on every token.
 *
 * Properties:
 *   - text: The raw markdown.
 *   - className: Class for the element holding the rendered HTML.
 */
const Markdown = memo(function Markdown(props: {
  text: string;
  className: string;
}) {
  return (
    <div
      className={props.className}
      dangerouslySetInnerHTML={{
        __html: DOMPurify.sanitize(marked.parse(props.text, { async: false })),
      }}
    />
  );
});

export interface AiModel {
  id: string;
  name: string;
}

/* Suggestion ids, each backed by a title, description and prompt under
 * chat.suggest in the catalog. The prompt is dropped into the composer, so
 * it is translated like the labels rather than sent verbatim in English.
 */
const SUGGESTION_IDS = [
  "overview",
  "access",
  "packing",
  "meals",
  "difficulty",
  "hazards",
] as const;

export interface ThinkingItem {
  kind: "thinking";
  text: string;
}

export interface ReplyItem {
  kind: "reply";
  text: string;
}

export interface CardItem {
  kind: "card";
  data: ChatCardData;
  resolve: (action_id: string | null) => void;
}

export type TurnItem = ThinkingItem | ReplyItem | CardItem;

export interface Turn {
  id: string;
  prompt: string;
  items: TurnItem[];
}

/* The assistant's reasoning for one turn, folded away once the turn ends.
 *
 * Properties:
 *   - text: The reasoning so far, as markdown.
 *   - finished: Whether the turn has ended, which folds the block.
 *
 * State:
 *   - folded: Whether the reasoning is collapsed.
 */
function ThinkingBlock(props: {
  text: string;
  finished: boolean;
}) {
  const { t } = useTranslation();
  const [folded, set_folded] = useState(false);

  useEffect(() => {
    if (props.finished)
      set_folded(true);
  }, [props.finished]);

  return (
    <div className="chat-thought">
      <button
        type="button"
        className="flat-btn chat-thought-header"
        aria-expanded={!folded}
        onClick={() => set_folded((f) => !f)}
      >
        <span className={mergeClasses("chevron", folded && "folded")}>
          {icon("chevron", 12)}
        </span>
        <span>{t("chat.thinking")}</span>
      </button>
      <div className={mergeClasses("chat-thought-body", folded && "folded")}>
        <Markdown className="chat-thought-text" text={props.text} />
      </div>
    </div>
  );
}

export function Chat(props: {
  chat_id: string;
  visible: boolean;
  turns: Turn[];
  busy: boolean;
  models: AiModel[];
  selected_model: string;
  on_model_change: (id: string) => void;
}) {
  const { t } = useTranslation();
  const [prompt, set_prompt] = useState("");
  const [sending, set_sending] = useState(false);
  const log_ref = useRef<HTMLDivElement>(null);
  const input_ref = useRef<HTMLTextAreaElement>(null);
  const sent_ref = useRef("");
  const idle = !props.busy && !sending;

  const model_label = props.models.find(
    (m) => m.id === props.selected_model
  )?.name ?? t("chat.model");

  const suggestions = SUGGESTION_IDS.map((id) => ({
    id,
    title: t(`chat.suggest.${id}.title`),
    description: t(`chat.suggest.${id}.description`),
    prompt: t(`chat.suggest.${id}.prompt`),
  }));

  const turns = props.turns;

  function on_suggestion_btn_click(text: string): void {
    set_prompt(text);
    input_ref.current?.focus();
  }

  /* Auto-follow: while the log is pinned to the bottom, keep it there as
   * new content streams in, and stop only once the user scrolls up.
   */
  const was_at_bottom = useRef(true);
  const last_top = useRef(0);
  useEffect(() => {
    const el = log_ref.current;
    if (!el)
      return;
    if (was_at_bottom.current) {
      el.scrollTop = el.scrollHeight;
      last_top.current = el.scrollTop;
    }
  });
  useEffect(() => {
    const el = log_ref.current;
    if (!el)
      return;
    const on_scroll = () => {
      const top = el.scrollTop;
      /* 32 is slack after which auto scrolling is disabled */
      const at_bottom = el.scrollHeight - top - el.clientHeight <= 32;
      if (at_bottom)
        was_at_bottom.current = true;
      else if (top < last_top.current)
        was_at_bottom.current = false;
      last_top.current = top;
    };
    el.addEventListener("scroll", on_scroll);
    return () => el.removeEventListener("scroll", on_scroll);
  }, []);

  function submit(): void {
    const text = prompt.trim();
    if (!text || !idle)
      return;
    sent_ref.current = text;
    set_sending(true);
    set_prompt("");
    void api.ask_assist(props.chat_id, props.selected_model, text)
      .finally(() => set_sending(false));
  }

  /* Stop the running turn: cancel the backend run and, if the composer is
   * empty, drop the sent prompt back in so the user can edit and resend. The
   * backend removes the streamed turn once the run is cancelled.
   */
  function stop(): void {
    void api.stop_assist(props.chat_id);
    if (sent_ref.current && prompt.trim().length === 0) {
      set_prompt(sent_ref.current);
      input_ref.current?.focus();
    }
  }

  function on_keydown(e: ReactKeyboardEvent<HTMLTextAreaElement>): void {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div className={mergeClasses("chat", !props.visible && "hidden")}>
      <div
        ref={log_ref}
        className={mergeClasses("chat-log", turns.length === 0 && "empty")}
      >
        <div className="chat-inner">
          {turns.length === 0 && (
            <div className="chat-welcome">
              <Text size={500} weight="bold" align="center" block>
                {t("chat.welcome")}
              </Text>
              <div className="chat-suggest">
                {suggestions.map((s) => (
                  <CompoundButton
                    key={s.id}
                    className="chat-suggest-item"
                    appearance="subtle"
                    secondaryContent={s.description}
                    onClick={() => on_suggestion_btn_click(s.prompt)}
                  >
                    {s.title}
                  </CompoundButton>
                ))}
              </div>
            </div>
          )}
          {turns.map((turn, ti) => {
            const active = ti === turns.length - 1;
            return (
              <div key={turn.id} className="chat-turn">
                <div className="chat-prompt">{turn.prompt}</div>
                {turn.items.map((node, ni) => {
                  switch (node.kind) {
                    case "thinking":
                      return (
                        <ThinkingBlock
                          key={ni}
                          text={node.text}
                          finished={!active || !props.busy}
                        />
                      );
                    case "reply":
                      return (
                        <Markdown
                          key={ni}
                          className="chat-reply"
                          text={node.text}
                        />
                      );
                    case "card":
                      return (
                        <ChatCardView
                          key={ni}
                          card={node.data}
                          on_action={(id) => node.resolve(id)}
                        />
                      );
                    default:
                      return null;
                  }
                })}
                {props.busy && active && (
                  <Spinner className="chat-spinner" size="huge" />
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div className="chat-composer">
        <div className="chat-composer-inner">
          <div className="chat-input-row">
            <textarea
              ref={input_ref}
              className="chat-input"
              rows={2}
              placeholder={t("chat.placeholder")}
              value={prompt}
              onChange={(e) => set_prompt(e.target.value)}
              onKeyDown={on_keydown}
              disabled={!idle}
            />
            <Button
              className="chat-send"
              appearance="primary"
              size="small"
              shape="circular"
              icon={idle ? icon("send", 18) : icon("stop", 18)}
              disabled={idle && prompt.trim().length == 0}
              title={idle ? t("chat.send") : t("chat.stop")}
              aria-label={idle ? t("chat.send_aria") : t("chat.stop_aria")}
              onClick={idle ? submit : stop}
            />
          </div>
          <div className="chat-composer-bar">
            <Menu>
              <MenuTrigger disableButtonEnhancement>
                <MenuButton
                  className="chat-model-btn"
                  appearance="subtle"
                  size="small"
                >
                  {model_label}
                </MenuButton>
              </MenuTrigger>
              <MenuPopover>
                <MenuList>
                  {props.models.map((m) => (
                    <MenuItem
                      key={m.id}
                      onClick={() => props.on_model_change(m.id)}
                    >
                      {m.name}
                    </MenuItem>
                  ))}
                </MenuList>
              </MenuPopover>
            </Menu>
          </div>
        </div>
      </div>
    </div>
  );
}
