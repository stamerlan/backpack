import { useEffect, useRef, useState } from "react";
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
import { icon } from "./icon";

export interface DialogAction {
  title: string;
  result?: unknown;
  size?: NonNullable<ButtonProps["size"]>;
  appearance?: NonNullable<ButtonProps["appearance"]>;
}

interface DialogModel {
  id: string;
  title: string;
  text: string;
  actions: DialogAction[];
  resolve: (value: unknown) => void;
}

function DialogView(props: {
  title: string;
  text: string;
  actions: DialogAction[];
  on_close: (value: unknown) => void;
}) {
  const [open, set_open] = useState(true);
  const done = useRef(false);

  const close = (value: unknown): void => {
    if (done.current)
      return;
    done.current = true;
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
       * value below.
       */
      if (!data.open)
        close(null);
    }}>
      <DialogSurface>
        <DialogBody>
          <DialogTitle
            action={
              <DialogTrigger action="close" disableButtonEnhancement>
                <Button appearance="transparent" aria-label="close"
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

/* A single host owns every open dialog as React state. show_dialog() adds a
 * request; closing removes it. Dialogs are independent and can stack (e.g. an
 * error over a save prompt). Sequencing is the backend's concern.
 */
let add_dialog: ((request: DialogModel) => void) | null = null;

export function DialogHost() {
  const [items, set_items] = useState<Set<DialogModel>>(new Set());

  useEffect(() => {
    add_dialog = (request) => set_items((s) => new Set(s).add(request));
      return () => { add_dialog = null; };
    }, []
  );

  const close = (request: DialogModel, value: unknown): void => {
    request.resolve(value);
    /* Let the exit animation finish before dropping the dialog. */
    setTimeout(() => {
      set_items((s) => {
        const next = new Set(s);
        next.delete(request);
        return next;
      });
    }, 300);
  };

  return (
    <>
      {[...items].map((request) => (
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

function show_dialog(
  title: string,
  text: string,
  actions?: Iterable<DialogAction>,
): Promise<unknown> {
  const add = add_dialog;
  if (add === null)
    throw new Error("dialog host is not mounted");
  return new Promise<unknown>((resolve) => {
    add({
      id: `dialog-${crypto.randomUUID()}`,
      title,
      text,
      actions: actions ? Array.from(actions) : [],
      resolve,
    });
  });
}

declare global {
  interface Window {
    show_dialog: typeof show_dialog;
  }
}

window.show_dialog = show_dialog;
