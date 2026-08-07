/* Hosts every banner the backend raises through window.notify. Banners are
 * independent and stack under the app bar; what to react to is the backend's
 * concern. window.clear_notify takes them all down at once.
 *
 * Properties:
 *   - (none): The backend drives the host through the globals above.
 *
 * State:
 *   - items: The live requests, oldest first.
 */
import { useEffect, useState } from "react";
import {
  Button,
  MessageBar,
  MessageBarActions,
  MessageBarBody,
  MessageBarGroup,
  MessageBarTitle,
} from "@fluentui/react-components";
import type { ButtonProps } from "@fluentui/react-components";
import { icon } from "./icon";
import "./notify.css";

export type NotifyIntent = "info" | "success" | "warning" | "error";

export interface NotifyAction {
  title: string;
  result?: unknown;
  appearance?: NonNullable<ButtonProps["appearance"]>;
}

interface NotifyRequest {
  id: string;
  message: string;
  title: string;
  intent: NotifyIntent;
  actions: NotifyAction[];
  resolve: (value: unknown) => void;
}

let add_msg: ((request: NotifyRequest) => void) | null = null;
let clear_msg: (() => void) | null = null;

export function NotifyHost() {
  const [items, set_items] = useState<NotifyRequest[]>([]);

  useEffect(() => {
    add_msg = (request) => set_items((all) => [...all, request]);
    clear_msg = () => set_items((all) => {
      for (const item of all)
        item.resolve(null);
      return [];
    });
    return () => { add_msg = null; clear_msg = null; };
  }, []);

  const close = (request: NotifyRequest, value: unknown): void => {
    request.resolve(value);
    set_items((all) => all.filter((item) => item !== request));
  };

  /* Collapse to nothing when empty so no border shows under the app bar. */
  if (items.length === 0)
    return null;

  return (
    <MessageBarGroup className="notify-group" animate="both">
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
