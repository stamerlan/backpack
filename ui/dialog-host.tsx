/* Hosts every dialog the backend opens through window.show_dialog. Dialogs
 * are independent and stack, an error over a save prompt for instance;
 * sequencing them is the backend's concern.
 *
 * Properties:
 *   - (none): Driven by the backend through ui-api.ts, not by a parent.
 *
 * State:
 *   - items: The open requests, oldest first. A closed one stays in the
 *     list until its exit animation has run.
 */
import { useEffect, useState } from "react";
import {
  Button,
  Dialog,
  DialogActions,
  DialogBody,
  DialogContent,
  DialogSurface,
  DialogTitle,
  DialogTrigger,
} from "@fluentui/react-components";
import type { ButtonProps } from "@fluentui/react-components";
import { useTranslation } from "react-i18next";
import { not_mounted } from "./ui-api";
import { icon } from "./icon";

export interface DialogAction {
  title: string;
  result?: unknown;
  size?: NonNullable<ButtonProps["size"]>;
  appearance?: NonNullable<ButtonProps["appearance"]>;
}

interface DialogRequest {
  id: string;
  title: string;
  text: string;
  actions: DialogAction[];
  resolve: (value: unknown) => void;
}

/* One dialog.
 *
 * Properties:
 *   - title: Heading text.
 *   - text: Body text.
 *   - actions: Footer buttons, none at all for a message-only dialog.
 *   - on_close: Reports the chosen value, or null when dismissed.
 *
 * State:
 *   - open: Whether the dialog is showing. It goes false before the host
 *     drops the request, which is what plays the exit animation.
 */
function DialogView(props: {
  title: string;
  text: string;
  actions: DialogAction[];
  on_close: (value: unknown) => void;
}) {
  const { t } = useTranslation();
  const [open, set_open] = useState(true);

  /* Settling a promise twice is a no-op, so the close paths need no guard
   * against one another.
   */
  const close = (value: unknown): void => {
    set_open(false);
    props.on_close(value);
  };

  const footer = props.actions.length > 0 ? (
    <DialogActions>
      {props.actions.map((action, index) => (
        <Button
          key={index}
          appearance={action.appearance}
          size={action.size}
          onClick={() => close(action.result ?? null)}
        >
          {action.title}
        </Button>
      ))}
    </DialogActions>
  ) : null;

  return (
    <Dialog open={open} modalType="modal" onOpenChange={(_event, data) => {
      /* Close button and Escape land here; action buttons deliver their own
       * value above.
       */
      if (!data.open)
        close(null);
    }}>
      <DialogSurface>
        <DialogBody>
          <DialogTitle
            action={
              <DialogTrigger action="close" disableButtonEnhancement>
                <Button
                  appearance="transparent"
                  aria-label={t("dialog.close")}
                  icon={icon("close")}
                />
              </DialogTrigger>
            }
          >
            {props.title}
          </DialogTitle>
          <DialogContent>{props.text}</DialogContent>
          {footer}
        </DialogBody>
      </DialogSurface>
    </Dialog>
  );
}

export function DialogHost() {
  const [items, set_items] = useState<DialogRequest[]>([]);

  useEffect(() => {
    window.show_dialog = (title, text, actions) =>
      new Promise((resolve) => set_items((all) => [...all, {
        id: `dialog-${crypto.randomUUID()}`,
        title,
        text,
        actions: actions ? Array.from(actions) : [],
        resolve,
      }]));
    return () => { window.show_dialog = not_mounted("dialog host"); };
  }, []);

  const close = (request: DialogRequest, value: unknown): void => {
    request.resolve(value);
    /* Let the exit animation finish before dropping the dialog. */
    setTimeout(() => {
      set_items((all) => all.filter((item) => item !== request));
    }, 300);
  };

  return (
    <>
      {items.map((request) => (
        <DialogView
          key={request.id}
          title={request.title}
          text={request.text}
          actions={request.actions}
          on_close={(value) => close(request, value)}
        />
      ))}
    </>
  );
}
