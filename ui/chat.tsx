import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import {
  Button,
  CompoundButton,
  makeStyles,
  Menu,
  MenuButton,
  MenuItem,
  MenuList,
  MenuPopover,
  MenuTrigger,
  mergeClasses,
  Spinner,
  Text,
  tokens,
} from "@fluentui/react-components";
import { marked } from "marked";
import DOMPurify from "dompurify";
import api from "./api";
import { icon } from "./icon";
import { ChatCardView, type ChatCardData } from "./card";

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

const use_styles = makeStyles({
  chat: {
    flex: "1 1 auto",
    minHeight: 0,
    display: "flex",
    flexDirection: "column"
  },
  /* A centered reading column holding both the log and the composer so the
   * input lines up under the messages. Its width fits three suggestion
   * buttons (min 190px, 4px gap) in a row but never four: three need 578px,
   * four would need 772px, so a width in between locks the grid to three.
   */
  body: {
    flex: "1 1 auto",
    minHeight: 0,
    width: "100%",
    maxWidth: "700px",
    margin: "0 auto",
    display: "flex",
    flexDirection: "column"
  },
  hidden: { display: "none" },
  log: {
    flex: "1 1 auto",
    minHeight: 0,
    overflowY: "auto",
    padding: "0 12px 12px",
    display: "flex",
    flexDirection: "column",
    gap: "4px"
  },
  /* An empty chat shrinks the log to its content so the
   * welcome text and the composer sit together near the
   * top instead of spread across the panel.
   */
  log_empty: { flex: "0 1 auto" },
  empty: {
    display: "flex",
    flexDirection: "column",
    gap: "10px",
    color: tokens.colorNeutralForeground3
  },
  suggest: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))",
    gap: "4px"
  },
  suggest_item: { justifyContent: "flex-start" },
  entry: {
    display: "flex",
    flexDirection: "column",
    gap: "8px",
    paddingBottom: "12px"
  },
  prompt_node: {
    padding: "8px 12px",
    whiteSpace: "pre-wrap",
    overflowWrap: "anywhere",
    userSelect: "text",
    cursor: "text",
    fontSize: tokens.fontSizeBase400,
    lineHeight: tokens.lineHeightBase400,
    color: tokens.colorNeutralForeground1,
    backgroundColor: tokens.colorNeutralBackground1,
    border: `1px solid ${tokens.colorNeutralStroke1}`,
    borderRadius: tokens.borderRadiusMedium,
    boxShadow:
      "0px 1px 2px rgba(0, 0, 0, 0.14), 0px 0px 2px rgba(0, 0, 0, 0.12)"
  },
  thought: {
    display: "flex",
    flexDirection: "column",
    fontSize: tokens.fontSizeBase300,
    lineHeight: tokens.lineHeightBase300,
    color: tokens.colorNeutralForeground3
  },
  thought_header: {
    display: "inline-flex",
    alignItems: "center",
    gap: "6px",
    alignSelf: "flex-start",
    padding: "2px 4px",
    border: "none",
    background: "transparent",
    color: tokens.colorNeutralForeground3,
    cursor: "pointer",
    borderRadius: tokens.borderRadiusSmall,
    ":hover": {
      color: tokens.colorNeutralForeground2,
      backgroundColor: tokens.colorNeutralBackground3
    }
  },
  thought_chevron: {
    display: "inline-flex",
    transitionProperty: "transform",
    transitionDuration: "0.15s",
    transitionTimingFunction: "ease"
  },
  thought_chevron_folded: { transform: "rotate(-90deg)" },
  thought_body: {
    display: "grid",
    gridTemplateRows: "1fr",
    transitionProperty: "grid-template-rows",
    transitionDuration: "0.18s",
    transitionTimingFunction: "ease"
  },
  thought_body_folded: { gridTemplateRows: "0fr" },
  thought_body_inner: {
    minHeight: 0,
    overflow: "hidden",
    paddingLeft: "2px",
    "& p": {
      marginTop: "0.25em",
      marginBottom: "0.25em"
    }
  },
  reply_node: {
    padding: "0 2px",
    overflowWrap: "anywhere",
    userSelect: "text",
    cursor: "text",
    fontSize: tokens.fontSizeBase400,
    lineHeight: tokens.lineHeightBase400,
    "& p": { marginTop: "0.25em", marginBottom: "0.25em" },
    "& pre": {
      backgroundColor: tokens.colorNeutralBackground3,
      padding: "8px",
      borderRadius: tokens.borderRadiusMedium,
      overflowX: "auto"
    },
    "& code": {
      fontFamily: tokens.fontFamilyMonospace,
      fontSize: tokens.fontSizeBase200
    },
    "& ul, & ol": { paddingLeft: "1.5em" },
  },
  spinner: {
    alignSelf: "center",
    marginTop: "16px",
    marginBottom: "16px"
  },
  composer: {
    flex: "none",
    display: "flex",
    flexDirection: "column",
    gap: "6px",
    padding: "10px 12px 12px"
  },
  input_wrap: {
    flex: "none",
    display: "flex",
    alignItems: "flex-end",
    gap: "8px"
  },
  input: {
    flex: "1 1 auto",
    minWidth: 0,
    resize: "none",
    border: `1px solid ${tokens.colorNeutralStroke1}`,
    borderRadius: tokens.borderRadiusMedium,
    padding: "8px 10px",
    fontFamily: "inherit",
    fontSize: "inherit",
    lineHeight: "inherit",
    color: "inherit",
    backgroundColor: tokens.colorNeutralBackground1,
    outline: "none",
    minHeight: "56px",
    maxHeight: "160px",
    overflowY: "auto",
    fieldSizing: "content" as "content"
  },
  send: {
    flex: "none",
    width: "26px",
    minWidth: "26px",
    maxWidth: "26px",
    height: "26px",
    padding: 0
  },
  composer_bar: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: "8px"
  },
  model_btn: {
    fontSize: tokens.fontSizeBase200,
    color: tokens.colorNeutralForeground3
  },
  delete_btn: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    width: "28px",
    height: "28px",
    flex: "none",
    padding: 0,
    border: "none",
    background: "transparent",
    color: tokens.colorNeutralForeground3,
    cursor: "pointer",
    borderRadius: tokens.borderRadiusSmall,
    ":hover": {
      color: tokens.colorNeutralForeground2,
      backgroundColor: tokens.colorNeutralBackground3
    }
  }
});

function ThinkingBlock(props: {
  text: string;
  finished: boolean;
}) {
  const styles = use_styles();
  const [folded, set_folded] = useState(false);

  useEffect(() => {
    if (props.finished)
      set_folded(true);
  }, [props.finished]);

  return (
    <div className={styles.thought}>
      <button
        type="button"
        className={styles.thought_header}
        aria-expanded={!folded}
        onClick={() => set_folded((f) => !f)}
      >
        <span
          className={mergeClasses(
            styles.thought_chevron,
            folded && styles.thought_chevron_folded
          )}
        >
          {icon("chevron", 12)}
        </span>
        <span>Thinking</span>
      </button>
      <div
        className={mergeClasses(
          styles.thought_body,
          folded && styles.thought_body_folded,
        )}
      >
        <div
          className={styles.thought_body_inner}
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
  const styles = use_styles();
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
    <div
      className={mergeClasses(styles.chat, !props.visible && styles.hidden)}
    >
      <div className={styles.body}>
        <div
          ref={log_ref}
          className={mergeClasses(
            styles.log, turns.length === 0 && styles.log_empty
          )}
        >
          {turns.length === 0 && (
            <div className={styles.empty}>
              <Text size={500} weight="bold" align="center" block>
                What should we plan?
              </Text>
              <div className={styles.suggest}>
                {SUGGESTIONS.map((s) => (
                  <CompoundButton
                    key={s.title}
                    className={styles.suggest_item}
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
              <div key={turn.id} className={styles.entry}>
                <div className={styles.prompt_node}>{turn.prompt}</div>
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
                          className={styles.reply_node}
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
                  <Spinner className={styles.spinner} size="huge" />
                )}
              </div>
            );
          })}
        </div>

        <div className={styles.composer}>
          <div className={styles.input_wrap}>
            <textarea
              ref={input_ref}
              className={styles.input}
              rows={2}
              placeholder="Ask the assistant..."
              value={prompt}
              onChange={(e) => set_prompt(e.target.value)}
              onKeyDown={on_keydown}
              disabled={props.busy}
            />
            <Button
              className={styles.send}
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
          <div className={styles.composer_bar}>
            <Menu>
              <MenuTrigger disableButtonEnhancement>
                <MenuButton
                  className={styles.model_btn}
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
              className={styles.delete_btn}
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
