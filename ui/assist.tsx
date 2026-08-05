import {
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import {
  makeStyles,
  mergeClasses,
  Tab,
  TabList,
  tokens,
} from "@fluentui/react-components";
import api from "./api";
import { icon } from "./icon";
import { Chat, type AiModel, type Turn, type TurnItem } from "./chat";
import type { ChatCardData } from "./card";

const ASSIST_MIN = 300;
const DEFAULT_WIDTH = 500;
/* The document keeps at least this width, so at the smallest window (600px)
 * the panel and the document each get half.
 */
const DOC_MIN = 300;

const use_styles = makeStyles({
  panel: {
    flex: "none",
    width: 0,
    height: "100%",
    position: "relative",
    overflow: "hidden",
    backgroundColor: tokens.colorNeutralBackground2,
    transform: "translateX(100%)",
    transitionProperty: "width",
    transitionDuration: "0.2s",
    transitionTimingFunction: "ease",
  },
  open: {
    transform: "none",
    borderLeft: `1px solid ${tokens.colorNeutralStroke1}`,
  },
  resizing: { transitionProperty: "none" },
  inner: {
    height: "100%",
    display: "flex",
    flexDirection: "column",
    minHeight: 0,
  },
  handle: {
    position: "absolute",
    top: 0,
    left: 0,
    width: "6px",
    height: "100%",
    cursor: "col-resize",
    zIndex: 2,
    touchAction: "none",
    ":hover": {
      backgroundColor: tokens.colorCompoundBrandStroke,
      opacity: 0.45,
    },
  },
  handle_active: {
    backgroundColor: tokens.colorCompoundBrandStroke,
    opacity: 0.45,
  },
  header: {
    display: "flex",
    flexDirection: "column",
    gap: "6px",
    padding: "8px 12px",
    flex: "none",
  },
  tabs_row: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
  },
  tabs: {
    flex: "1 1 auto",
    minWidth: 0,
    overflowX: "auto",
    overflowY: "hidden",
    /* A fixed height reserves room for the horizontal scrollbar: when tabs
     * overflow on a new chat the bar eats into this height instead of growing
     * the strip, so the content below never jumps.
     */
    height: "40px",
    boxSizing: "border-box",
    scrollbarWidth: "thin",
  },
  icon_btn: {
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
      backgroundColor: tokens.colorNeutralBackground3,
    },
  },
  chats: {
    flex: "1 1 auto",
    minHeight: 0,
    display: "flex",
    flexDirection: "column",
  },
});

interface ChatMeta {
  id: string;
  title: string;
}

const EMPTY_TURNS: Turn[] = [];

/* Owns every chat's turn log and busy flag so restore does not depend on a
 * child Chat having mounted and registered itself first. Turns are keyed by
 * chat id in one state record; new_turn/append_* mutate that record directly,
 * so a call always lands on state that exists the moment the chat was added.
 */
class AssistView {
  #chats: ChatMeta[];
  #set_chats: Dispatch<SetStateAction<ChatMeta[]>>;
  #active: string;
  #set_active: Dispatch<SetStateAction<string>>;
  #models: AiModel[];
  #set_models: Dispatch<SetStateAction<AiModel[]>>;
  #selected_model: string;
  #set_selected_model: Dispatch<SetStateAction<string>>;
  #turns: Record<string, Turn[]>;
  #set_turns: Dispatch<SetStateAction<Record<string, Turn[]>>>;
  #busy: Record<string, boolean>;
  #set_busy: Dispatch<SetStateAction<Record<string, boolean>>>;

  constructor() {
    [this.#chats, this.#set_chats]   = useState<ChatMeta[]>([]);
    [this.#active, this.#set_active] = useState("");
    [this.#models, this.#set_models] = useState<AiModel[]>([]);
    [this.#selected_model, this.#set_selected_model] = useState("");
    [this.#turns, this.#set_turns] = useState<Record<string, Turn[]>>({});
    [this.#busy, this.#set_busy] = useState<Record<string, boolean>>({});
  }

  get chats(): ChatMeta[] { return this.#chats; }
  get active(): string { return this.#active; }
  get models(): AiModel[] { return this.#models; }

  get selected_model(): string { return this.#selected_model; }
  set selected_model(id: string) { this.#set_selected_model(id); }

  turns_of(chat_id: string): Turn[] {
    return this.#turns[chat_id] ?? EMPTY_TURNS;
  }

  busy_of(chat_id: string): boolean {
    return this.#busy[chat_id] ?? false;
  }

  clear(): void {
    this.#set_chats([]);
    this.#set_active("");
    this.#set_turns({});
    this.#set_busy({});
  }

  set_models(models: AiModel[]): void {
    this.#set_models(models);
    if (models.length > 0 && !this.#selected_model)
      this.#set_selected_model(models[0]!.id);
  }

  new_chat(chat_id: string, title: string): void {
    this.#set_chats((c) => [...c, { id: chat_id, title: title || "New chat" }]);
  }

  del_chat(chat_id: string): void {
    this.#set_chats((c) => c.filter((ch) => ch.id !== chat_id));
    this.#set_turns((t) => drop_key(t, chat_id));
    this.#set_busy((b) => drop_key(b, chat_id));
    this.#set_active((a) => a === chat_id ? "" : a);
  }

  set_active_chat(chat_id: string): void {
    this.#set_active(chat_id);
  }

  set_chat_title(chat_id: string, title: string): void {
    this.#set_chats((c) =>
      c.map((ch) => ch.id === chat_id ? { ...ch, title } : ch));
  }

  new_turn(chat_id: string, turn_id: string, prompt: string): void {
    this.#set_turns((t) => ({
      ...t,
      [chat_id]: [...(t[chat_id] ?? []), { id: turn_id, prompt, items: [] }],
    }));
    this.#set_busy((b) => ({ ...b, [chat_id]: true }));
  }

  del_turn(chat_id: string, turn_id: string): void {
    this.#set_turns((t) => {
      const cur = t[chat_id];
      if (cur === undefined)
        return t;
      return { ...t, [chat_id]: cur.filter((x) => x.id !== turn_id) };
    });
  }

  append_thinking(chat_id: string, text: string): void {
    this.#add_item(chat_id, { kind: "thinking", text });
  }

  append_reply(chat_id: string, text: string): void {
    this.#add_item(chat_id, { kind: "reply", text });
  }

  /* Return a promise that settles when the user clicks a card action, so the
   * backend future (add_done_callback) fires with the chosen action id. A card
   * with no actions has nothing to click, so it resolves null right away.
   */
  add_card(chat_id: string, card: ChatCardData): Promise<string | null> {
    return new Promise<string | null>((resolve) => {
      this.#add_item(chat_id, { kind: "card", data: card, resolve });
      if (card.actions.length === 0)
        resolve(null);
    });
  }

  end_turn(chat_id: string): void {
    this.#set_busy((b) => ({ ...b, [chat_id]: false }));
  }

  /* Append an item to the chat's last turn. Consecutive thinking or reply items
   * are merged so a token stream coalesces into one block; cards always start a
   * new item.
   */
  #add_item(chat_id: string, item: TurnItem): void {
    this.#set_turns((t) => {
      const turns = t[chat_id];
      if (turns === undefined || turns.length === 0)
        return t;
      const last_turn = turns[turns.length - 1]!;
      const last_turn_items = last_turn.items;
      const last_item = last_turn_items[last_turn_items.length - 1];

      let new_items: TurnItem[];

      if ((last_item?.kind === "thinking" && item.kind === "thinking") ||
          (last_item?.kind === "reply"    && item.kind === "reply"))
        new_items = [
          ...last_turn_items.slice(0, -1),
          { kind: item.kind, text: last_item.text + item.text },
        ];
      else
        new_items = [...last_turn_items, item];

      return {
        ...t,
        [chat_id]: [...turns.slice(0, -1), { ...last_turn, items: new_items }],
      };
    });
  }
}

function drop_key<V>(
  rec: Record<string, V>, key: string
): Record<string, V> {
  if (!(key in rec))
    return rec;
  const { [key]: _removed, ...rest } = rec;
  return rest;
}

export function Assist(props: {
  open: boolean;
  on_close: () => void;
}) {
  const styles = use_styles();
  const assist = new AssistView();
  const [width, set_width] = useState(DEFAULT_WIDTH);
  const dragging = useRef(false);
  const [resizing, set_resizing] = useState(false);
  const [win_width, set_win_width] = useState(window.innerWidth);

  useEffect(() => {
    window.assist = assist;
    return () => { window.assist = null; };
  });

  useEffect(() => {
    const on_resize = () => set_win_width(window.innerWidth);
    window.addEventListener("resize", on_resize);
    return () => window.removeEventListener("resize", on_resize);
  }, []);

  const open_width = Math.min(width, win_width - DOC_MIN);

  useEffect(() => {
    function on_move(e: PointerEvent): void {
      if (!dragging.current)
        return;
      let w = window.innerWidth - e.clientX;
      w = Math.max(ASSIST_MIN, Math.min(window.innerWidth - DOC_MIN, w));
      set_width(w);
    }
    function on_up(): void {
      if (!dragging.current)
        return;
      dragging.current = false;
      set_resizing(false);
    }
    window.addEventListener("pointermove", on_move);
    window.addEventListener("pointerup", on_up);
    return () => {
      window.removeEventListener("pointermove", on_move);
      window.removeEventListener("pointerup", on_up);
    };
  }, []);

  const chat_ids = assist.chats.map((c) => c.id);
  const active_id = assist.active || chat_ids[0] || "";
  return (
    <aside
      className={mergeClasses(
        styles.panel,
        props.open && styles.open,
        resizing && styles.resizing,
      )}
      style={props.open ? { width: `${open_width}px` } : undefined}
      aria-label="AI assistant"
      inert={!props.open ? true : undefined}
    >
      <div
        className={mergeClasses(
          styles.handle,
          resizing && styles.handle_active,
        )}
        title="Drag to resize"
        onPointerDown={(e) => {
          e.preventDefault();
          dragging.current = true;
          set_resizing(true);
        }}
      />

      <div
        className={styles.inner}
        style={{ width: `${open_width}px` }}
      >
        <div className={styles.header}>
          <div className={styles.tabs_row}>
            <TabList
              className={styles.tabs}
              size="small"
              selectedValue={active_id}
              onTabSelect={(_e, d) => {
                assist.set_active_chat(d.value as string);
              }}
            >
              {assist.chats.map((c) => {
                const label = c.title || "New chat";
                return (
                  <Tab key={c.id} value={c.id} title={label}>
                    {label.length > 30 ? label.slice(0, 28) + "..." : label}
                  </Tab>
                );
              })}
            </TabList>
            <button
              type="button"
              className={styles.icon_btn}
              title="New chat"
              aria-label="New chat"
              onClick={() => { void api.add_chat(); }}
            >
              {icon("doc-add", 16)}
            </button>
          </div>
        </div>

        <div className={styles.chats}>
          {assist.chats.map((c) => (
            <Chat
              key={c.id}
              chat_id={c.id}
              visible={c.id === active_id}
              turns={assist.turns_of(c.id)}
              busy={assist.busy_of(c.id)}
              models={assist.models}
              selected_model={assist.selected_model}
              on_model_change={(m) => { assist.selected_model = m; }}
            />
          ))}
        </div>
      </div>
    </aside>
  );
}

declare global {
  interface Window {
    assist: AssistView | null;
  }
}

window.assist = null;
