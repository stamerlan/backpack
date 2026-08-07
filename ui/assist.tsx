import {
  useEffect,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import { mergeClasses, Tab, TabList } from "@fluentui/react-components";
import api from "./api";
import { icon } from "./icon";
import { Chat, type AiModel, type Turn, type TurnItem } from "./chat";
import type { ChatCardData } from "./card";
import "./assist.css";

const ASSIST_MIN = 300;
const DEFAULT_WIDTH = 500;
/* The document keeps at least this width, so at the smallest window (600px)
 * the panel and the document each get half. assist.css caps the panel with
 * the same number.
 */
const DOC_MIN = 300;

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
}) {
  const assist = new AssistView();
  const [width, set_width] = useState(DEFAULT_WIDTH);
  const [resizing, set_resizing] = useState(false);

  useEffect(() => {
    window.assist = assist;
    return () => { window.assist = null; };
  });

  /* Listening only while a drag runs keeps the handlers free of any flag
   * telling them whether this pointer belongs to a resize.
   */
  useEffect(() => {
    if (!resizing)
      return;
    const on_move = (e: PointerEvent): void => {
      const w = window.innerWidth - e.clientX;
      set_width(
        Math.max(ASSIST_MIN, Math.min(window.innerWidth - DOC_MIN, w))
      );
    };
    const on_up = (): void => set_resizing(false);
    window.addEventListener("pointermove", on_move);
    window.addEventListener("pointerup", on_up);
    return () => {
      window.removeEventListener("pointermove", on_move);
      window.removeEventListener("pointerup", on_up);
    };
  }, [resizing]);

  const chat_ids = assist.chats.map((c) => c.id);
  const active_id = assist.active || chat_ids[0] || "";
  return (
    <aside
      className={mergeClasses(
        "assist-panel",
        props.open && "open",
        resizing && "resizing",
      )}
      style={props.open ? { width: `${width}px` } : undefined}
      aria-label="AI assistant"
      inert={!props.open ? true : undefined}
    >
      <div
        className={mergeClasses("assist-handle", resizing && "active")}
        title="Drag to resize"
        onPointerDown={(e) => {
          e.preventDefault();
          set_resizing(true);
        }}
      />

      <div className="assist-inner" style={{ width: `${width}px` }}>
        <div className="assist-header">
          <div className="assist-tabs-row">
            <TabList
              className="assist-tabs"
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
              className="assist-icon-btn"
              title="New chat"
              aria-label="New chat"
              onClick={() => { void api.add_chat(); }}
            >
              {icon("doc-add", 16)}
            </button>
          </div>
        </div>

        <div className="assist-chats">
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
