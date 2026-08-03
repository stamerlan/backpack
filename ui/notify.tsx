import { useEffect, useState } from "react";
import {
  makeStyles,
  tokens,
  Button,
  MessageBar,
  MessageBarActions,
  MessageBarBody,
  MessageBarGroup,
  MessageBarTitle,
} from "@fluentui/react-components";
import type { ButtonProps } from "@fluentui/react-components";
import { icon } from "./icon";

export type NotifyIntent = "info" | "success" | "warning" | "error";

export interface NotifyAction {
  title: string;
  result?: unknown;
  appearance?: NonNullable<ButtonProps["appearance"]>;
}

interface NotifyView {
  id: string;
  message: string;
  title: string;
  intent: NotifyIntent;
  actions: NotifyAction[];
  resolve: (value: unknown) => void;
}

const use_styles = makeStyles({
  group: {
    flex: "none",
    display: "flex",
    flexDirection: "column",
    gap: "4px",
    padding: "4px 8px",
    borderBottom: `1px solid ${tokens.colorNeutralStroke2}`,
  },
});

/* A single host owns every live banner as React state. notify() adds a
 * request; the close button or an action removes it. Banners are independent
 * and stack under the app bar; the backend decides what to react to.
 */
let add_msg: ((request: NotifyView) => void) | null = null;
let clear_msg: (() => void) | null = null;

export function NotifyHost() {
  const styles = use_styles();
  const [items, set_items] = useState<NotifyView[]>([]);

  useEffect(() => {
    add_msg = (request) => set_items((s) => [...s, request]);
    clear_msg = () => set_items((s) => {
      for (const item of s)
        item.resolve(null);
      return [];
    });
    return () => { add_msg = null; clear_msg = null; };
  }, []);

  const close = (request: NotifyView, value: unknown): void => {
    request.resolve(value);
    set_items((s) => s.filter((item) => item !== request));
  };

  /* Collapse to nothing when empty so no border shows under the app bar. */
  if (items.length === 0)
    return null;

  return (
    <MessageBarGroup className={styles.group} animate="both">
      {items.map((msg) => (
        <MessageBar key={msg.id} intent={msg.intent}>
          <MessageBarBody>
            {msg.title && (
              <MessageBarTitle>{msg.title}</MessageBarTitle>
            )}
            {msg.message}
          </MessageBarBody>
          <MessageBarActions
            containerAction={
              <Button
                appearance="transparent"
                aria-label="dismiss"
                icon={icon("close")}
                onClick={() => close(msg, null)}
              />
            }
          >
            {msg.actions.map((action, index) => (
              <Button
                key={index}
                appearance={action.appearance}
                onClick={() => close(msg, action.result ?? null)}
              >
                {action.title}
              </Button>
            ))}
          </MessageBarActions>
        </MessageBar>
      ))}
    </MessageBarGroup>
  );
}

function notify(
  message: string,
  intent: NotifyIntent = "info",
  title = "",
  actions?: Iterable<NotifyAction>,
): Promise<unknown> {
  const add = add_msg;
  if (add === null)
    throw new Error("notify host is not mounted");
  return new Promise<unknown>((resolve) => {
    add({
      id: `note-${crypto.randomUUID()}`,
      message,
      title,
      intent,
      actions: actions ? Array.from(actions) : [],
      resolve,
    });
  });
}

function clear_notify(): void {
  clear_msg?.();
}

declare global {
  interface Window {
    notify: typeof notify;
    clear_notify: typeof clear_notify;
  }
}

window.notify = notify;
window.clear_notify = clear_notify;
