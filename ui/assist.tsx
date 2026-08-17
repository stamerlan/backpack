/* The assistant panel: a resizable strip along the right edge holding one tab
 * per chat with that chat's conversation below it. While mounted it publishes
 * window.assist, the surface the backend streams turns through, so the
 * methods of AssistApi mirror Assist in src/backpack/ui.py.
 *
 * Properties:
 *   - open: Whether the panel is slid out.
 *
 * State:
 *   - chats: One entry per chat, in tab order.
 *   - active: Chat the user selected, empty until they pick one.
 *   - models: Assistant models offered in the composer menu.
 *   - selected_model: Model the user picked, empty meaning the first.
 *   - turns: Turn log per chat id. Held here rather than in each Chat so a
 *     restored chat has its history before that component mounts.
 *   - busy: Whether a turn is still streaming, per chat id.
 *   - width: Panel width in pixels, set by dragging the handle.
 *   - resizing: Whether such a drag is running.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { mergeClasses, Tab, TabList } from "@fluentui/react-components";
import { useTranslation } from "react-i18next";
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

/* Everything the backend may call on window.assist. */
export interface AssistApi {
  clear(): void;
  set_models(models: AiModel[]): void;
  new_chat(chat_id: string, title: string): void;
  del_chat(chat_id: string): void;
  set_active_chat(chat_id: string): void;
  set_chat_title(chat_id: string, title: string): void;
  new_turn(chat_id: string, turn_id: string, prompt: string): void;
  del_turn(chat_id: string, turn_id: string): void;
  append_thinking(chat_id: string, text: string): void;
  append_reply(chat_id: string, text: string): void;
  /* Settles when the user clicks a card action, so the backend future
   * (add_done_callback) fires with the chosen action id. A card with no
   * actions has nothing to click, so it resolves null right away.
   */
  add_card(chat_id: string, card: ChatCardData): Promise<string | null>;
  end_turn(chat_id: string): void;
}

function drop_key<V>(rec: Record<string, V>, key: string): Record<string, V> {
  if (!(key in rec))
    return rec;
  const { [key]: _removed, ...rest } = rec;
  return rest;
}

export function Assist(props: {
  open: boolean;
}) {
  const { t } = useTranslation();
  const [chats, set_chats] = useState<ChatMeta[]>([]);
  const [active, set_active] = useState("");
  const [models, set_models] = useState<AiModel[]>([]);
  const [selected_model, set_selected_model] = useState("");
  const [turns, set_turns] = useState<Record<string, Turn[]>>({});
  const [busy, set_busy] = useState<Record<string, boolean>>({});
  const [unread, set_unread] = useState<Record<string, boolean>>({});
  const [width, set_width] = useState(DEFAULT_WIDTH);
  const [resizing, set_resizing] = useState(false);
  const active_ref = useRef("");

  /* Built once: the state setters it closes over never change identity, so
   * the backend always reaches the live panel through the same object.
   */
  const assist = useMemo<AssistApi>(() => {
    /* Append an item to the chat's last turn. Consecutive thinking or reply
     * items are merged so a token stream coalesces into one block; cards
     * always start a new item.
     */
    const add_item = (chat_id: string, item: TurnItem): void => {
      set_turns((all) => {
        const chat_turns = all[chat_id];
        if (chat_turns === undefined || chat_turns.length === 0)
          return all;
        const last_turn = chat_turns[chat_turns.length - 1]!;
        const items = last_turn.items;
        const last = items[items.length - 1];

        const merged =
          (last?.kind === "thinking" && item.kind === "thinking") ||
          (last?.kind === "reply" && item.kind === "reply")
            ? [...items.slice(0, -1),
               { kind: item.kind, text: last.text + item.text }]
            : [...items, item];

        return {
          ...all,
          [chat_id]: [
            ...chat_turns.slice(0, -1), { ...last_turn, items: merged },
          ],
        };
      });
    };

    return {
      set_models,
      set_active_chat: set_active,
      clear() {
        set_chats([]);
        set_active("");
        set_turns({});
        set_busy({});
        set_unread({});
      },
      new_chat(chat_id, title) {
        set_chats((all) => [...all, { id: chat_id, title }]);
      },
      del_chat(chat_id) {
        set_chats((all) => all.filter((c) => c.id !== chat_id));
        set_turns((all) => drop_key(all, chat_id));
        set_busy((all) => drop_key(all, chat_id));
        set_unread((all) => drop_key(all, chat_id));
        set_active((cur) => cur === chat_id ? "" : cur);
      },
      set_chat_title(chat_id, title) {
        set_chats((all) =>
          all.map((c) => c.id === chat_id ? { ...c, title } : c));
      },
      new_turn(chat_id, turn_id, prompt) {
        set_turns((all) => ({
          ...all,
          [chat_id]: [
            ...(all[chat_id] ?? []), { id: turn_id, prompt, items: [] },
          ],
        }));
        set_busy((all) => ({ ...all, [chat_id]: true }));
      },
      del_turn(chat_id, turn_id) {
        set_turns((all) => {
          const chat_turns = all[chat_id];
          if (chat_turns === undefined)
            return all;
          return {
            ...all,
            [chat_id]: chat_turns.filter((t) => t.id !== turn_id),
          };
        });
      },
      append_thinking(chat_id, text) {
        add_item(chat_id, { kind: "thinking", text });
      },
      append_reply(chat_id, text) {
        add_item(chat_id, { kind: "reply", text });
      },
      add_card(chat_id, card) {
        return new Promise<string | null>((resolve) => {
          add_item(chat_id, { kind: "card", data: card, resolve });
          if (card.actions.length === 0)
            resolve(null);
        });
      },
      end_turn(chat_id) {
        set_busy((all) => ({ ...all, [chat_id]: false }));
        if (chat_id !== active_ref.current)
          set_unread((all) => ({ ...all, [chat_id]: true }));
      },
    };
  }, []);

  useEffect(() => {
    window.assist = assist;
    return () => { window.assist = null; };
  }, [assist]);

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

  /* Both fall back to the first entry, so neither needs seeding when the
   * chats or the models arrive.
   */
  const active_id = active || chats[0]?.id || "";
  const model_id = selected_model || models[0]?.id || "";

  /* Whatever chat is on screen is by definition read: track it for end_turn
   * and drop its flag the moment it becomes visible.
   */
  useEffect(() => {
    active_ref.current = active_id;
    set_unread((all) => drop_key(all, active_id));
  }, [active_id]);

  return (
    <aside
      className={mergeClasses(
        "assist-panel",
        props.open && "open",
        resizing && "resizing",
      )}
      style={props.open ? { width: `${width}px` } : undefined}
      aria-label={t("assist.label")}
      inert={!props.open ? true : undefined}
    >
      <div
        className={mergeClasses("assist-handle", resizing && "active")}
        title={t("assist.resize")}
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
              onTabSelect={(_e, d) => set_active(d.value as string)}
            >
              {chats.map((c) => {
                const label = c.title || t("assist.new_chat");
                const shown =
                  label.length > 30 ? label.slice(0, 28) + "..." : label;
                const close = t("assist.close_chat");
                const do_close = () => { void api.del_chat(c.id); };
                return (
                  <Tab key={c.id} value={c.id} title={label}>
                    <span
                      className={mergeClasses(
                        "assist-tab",
                        c.id === active_id && "selected",
                      )}
                    >
                      <span className="assist-tab-label">{shown}</span>
                      {unread[c.id] && c.id !== active_id && (
                        <span
                          className="assist-tab-badge"
                          title={t("assist.unread")}
                          aria-label={t("assist.unread")}
                        />
                      )}
                      <span
                        className="assist-tab-close"
                        role="button"
                        tabIndex={0}
                        title={close}
                        aria-label={close}
                        onClick={(e) => {
                          e.stopPropagation();
                          do_close();
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            e.stopPropagation();
                            do_close();
                          }
                        }}
                      >
                        {icon("close", 12)}
                      </span>
                    </span>
                  </Tab>
                );
              })}
            </TabList>
            <button
              type="button"
              className="icon-btn"
              title={t("assist.new_chat")}
              aria-label={t("assist.new_chat")}
              onClick={() => { void api.add_chat(); }}
            >
              {icon("doc-add", 16)}
            </button>
          </div>
        </div>

        <div className="assist-chats">
          {chats.map((c) => (
            <Chat
              key={c.id}
              chat_id={c.id}
              visible={c.id === active_id}
              turns={turns[c.id] ?? EMPTY_TURNS}
              busy={busy[c.id] ?? false}
              models={models}
              selected_model={model_id}
              on_model_change={set_selected_model}
            />
          ))}
        </div>
      </div>
    </aside>
  );
}
