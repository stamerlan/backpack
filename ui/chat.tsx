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
import { marked } from "marked";
import DOMPurify from "dompurify";
import api from "./api";
import { icon } from "./icon";
import { ChatCardView, type ChatCardData } from "./card";
import "./chat.css";

marked.use({ breaks: true });

function render_md(raw: string): string {
  return DOMPurify.sanitize(marked.parse(raw, { async: false }));
}

export interface AiModel {
  id: string;
  name: string;
}

interface Suggestion {
  title: string;
  description: string;
  prompt: string;
}

const SUGGESTIONS: Suggestion[] = [
  {
    title: "Trip overview",
    description: "Fill in titles and notes",
    prompt:
      "Write a short overview of this trip into the trip notes, and give " +
      "each route a clear title and summary. Find huts, shelters, campsites, " +
      "water sources and other POI near my route, with access and opening " +
      "details. Include as much details as possible including terrain, " +
      "scenery, water sources."
  },
  {
    title: "Getting there",
    description: "Access, shuttles, bailouts",
    prompt:
      "How do I get to the start and back from the end of this route - " +
      "parking, shuttles and public transport - and where are the bailout " +
      "points?"
  },
  {
    title: "Packing list",
    description: "Gear for terrain and season",
    prompt:
      "Build a packing list for this route and season, and show where I can " +
      "cut base weight."
  },
  {
    title: "Meals and water",
    description: "Calories, weight, refill points",
    prompt:
      "Plan meals for each day with nutrition and pack weight, and mark " +
      "where I can refill water."
  },
  {
    title: "Difficulty and pace",
    description: "Effort, daily distance, tips&tricks",
    prompt:
      "Assess the difficulty and daily pacing of this route for my fitness, " +
      "give some tips and tricks."
  },
  {
    title: "Hazards and permits",
    description: "Safety, closures, regulations",
    prompt:
      "List hazards, permit requirements and seasonal closures along this " +
      "route."
  },
];

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
  const [folded, set_folded] = useState(false);

  useEffect(() => {
    if (props.finished)
      set_folded(true);
  }, [props.finished]);

  return (
    <div className="chat-thought">
      <button
        type="button"
        className="chat-thought-header"
        aria-expanded={!folded}
        onClick={() => set_folded((f) => !f)}
      >
        <span
          className={mergeClasses("chat-thought-chevron", folded && "folded")}
        >
          {icon("chevron", 12)}
        </span>
        <span>Thinking</span>
      </button>
      <div className={mergeClasses("chat-thought-body", folded && "folded")}>
        <div
          className="chat-thought-text"
          dangerouslySetInnerHTML={{
            __html: render_md(props.text),
          }}
        />
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
  const [prompt, set_prompt] = useState("");
  const log_ref = useRef<HTMLDivElement>(null);
  const input_ref = useRef<HTMLTextAreaElement>(null);
  const sending = useRef(false);

  const model_label = props.models.find(
    (m) => m.id === props.selected_model
  )?.name ?? "Model";

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
    if (!text || props.busy || sending.current)
      return;
    sending.current = true;
    set_prompt("");
    void api.ask_assist(props.chat_id, props.selected_model, text)
      .finally(() => { sending.current = false; });
  }

  function on_keydown(e: ReactKeyboardEvent<HTMLTextAreaElement>): void {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  return (
    <div className={mergeClasses("chat", !props.visible && "hidden")}>
      <div className="chat-body">
        <div
          ref={log_ref}
          className={mergeClasses("chat-log", turns.length === 0 && "empty")}
        >
          {turns.length === 0 && (
            <div className="chat-welcome">
              <Text size={500} weight="bold" align="center" block>
                What should we plan?
              </Text>
              <div className="chat-suggest">
                {SUGGESTIONS.map((s) => (
                  <CompoundButton
                    key={s.title}
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
                        <div
                          key={ni}
                          className="chat-reply"
                          dangerouslySetInnerHTML={{
                            __html: render_md(node.text),
                          }}
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

        <div className="chat-composer">
          <div className="chat-input-row">
            <textarea
              ref={input_ref}
              className="chat-input"
              rows={2}
              placeholder="Ask the assistant..."
              value={prompt}
              onChange={(e) => set_prompt(e.target.value)}
              onKeyDown={on_keydown}
              disabled={props.busy}
            />
            <Button
              className="chat-send"
              appearance="primary"
              size="small"
              shape="circular"
              icon={icon("send", 18)}
              disabled={prompt.trim().length == 0 || props.busy}
              title="Send"
              aria-label="Send message"
              onClick={submit}
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
            <button
              type="button"
              className="chat-delete-btn"
              title="Delete chat"
              aria-label="Delete current chat"
              onClick={() => void api.del_chat(props.chat_id)}
            >
              {icon("trash", 15)}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
