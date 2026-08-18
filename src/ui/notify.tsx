/* Hosts every banner the backend raises through window.notify. Banners are
 * independent and stack under the app bar; what to react to is the backend's
 * concern. window.clear_notify takes them all down at once.
 *
 * Properties:
 *   - (none): Driven by the backend through ui-api.ts, not by a parent.
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
import { useTranslation } from "react-i18next";
import { not_mounted } from "./ui-api";
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

export function NotifyHost() {
  const { t } = useTranslation();
  const [items, set_items] = useState<NotifyRequest[]>([]);

  useEffect(() => {
    window.notify = (message, intent = "info", title = "", actions) =>
      new Promise((resolve) => set_items((all) => [...all, {
        id: `note-${crypto.randomUUID()}`,
        message,
        title,
        intent,
        actions: actions ? Array.from(actions) : [],
        resolve,
      }]));
    window.clear_notify = () => set_items((all) => {
      for (const item of all)
        item.resolve(null);
      return [];
    });
    return () => {
      window.notify = not_mounted("notify host");
      window.clear_notify = () => {};
    };
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
                aria-label={t("notify.dismiss")}
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