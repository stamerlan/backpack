import { useState, type Dispatch, type SetStateAction } from "react";
import {
  Button,
  Card,
  Input,
  Textarea,
  makeStyles,
  mergeClasses,
  tokens,
} from "@fluentui/react-components";
import api from "./api";
import { icon } from "./icon";
import { RouteMap, type MapOverlay } from "./route-map";

const use_styles = makeStyles({
  card: {
    display: "flex",
    flexDirection: "column",
    gap: "8px",
    padding: "8px 12px 12px",
  },
  body: {
    display: "flex",
    flexDirection: "column",
    gap: "8px",
    minWidth: 0,
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
  },
  chevron: {
    display: "inline-flex",
    transition: "transform 0.15s ease",
  },
  chevron_folded: {
    transform: "rotate(-90deg)",
  },
  title: {
    flex: "1 1 auto",
    minWidth: 0,
  },
  title_input: {
    fontSize: tokens.fontSizeBase400,
    fontWeight: tokens.fontWeightSemibold,
  },
  notes_area: {
    minHeight: "120px",
  },
});

class RouteView {
  #id: string;
  #title: string;
  #set_title: Dispatch<SetStateAction<string>>;
  #notes: string;
  #set_notes: Dispatch<SetStateAction<string>>;
  #folded: boolean;
  #set_folded: Dispatch<SetStateAction<boolean>>;
  #on_remove: (id: string) => void;

  constructor(
    id: string,
    title: string,
    notes: string,
    on_remove: (id: string) => void,
  ) {
    this.#id = id;
    [this.#title, this.#set_title] = useState(title);
    [this.#notes, this.#set_notes] = useState(notes);
    [this.#folded, this.#set_folded] = useState(false);
    this.#on_remove = on_remove;
  }

  get title(): string {
    return this.#title;
  }

  set title(title: string) {
    this.#set_title(title);
  }

  get notes(): string {
    return this.#notes;
  }

  set notes(notes: string) {
    this.#set_notes(notes);
  }

  get folded(): boolean {
    return this.#folded;
  }

  toggle_fold(): void {
    this.#set_folded((folded) => !folded);
  }

  commit(): void {
    void api.set_route_info(this.#id, this.#title, this.#notes);
  }

  remove(): void {
    void api.remove_route(this.#id);
    this.#on_remove(this.#id);
  }
}

export function RouteCard(props: {
  id: string;
  title: string;
  notes: string;
  overlay: MapOverlay;
  on_remove: (id: string) => void;
}) {
  const styles = use_styles();
  const route = new RouteView(
    props.id, props.title, props.notes, props.on_remove
  );

  return (
    <Card className={styles.card}>
      <div className={styles.header}>
        <Button
          appearance="subtle"
          size="small"
          title={route.folded ? "Unfold route" : "Fold route"}
          aria-label={route.folded ? "Unfold route" : "Fold route"}
          aria-expanded={!route.folded}
          icon={
            <span
              className={mergeClasses(
                styles.chevron, route.folded && styles.chevron_folded
              )}
            >
              {icon("chevron", 12)}
            </span>
          }
          onClick={() => route.toggle_fold()}
        />
        <Input
          className={styles.title}
          appearance="underline"
          placeholder="Untitled route"
          value={route.title}
          input={{ className: styles.title_input }}
          onChange={(_event, data) => { route.title = data.value; }}
          onKeyDown={(event) => {
            /* Enter commits the same way leaving the field does. */
            if (event.key === "Enter")
              event.currentTarget.blur();
          }}
          onBlur={() => route.commit()}
        />
        <Button
          appearance="subtle"
          title="Delete route"
          aria-label="Delete route"
          icon={icon("trash", 16)}
          onClick={() => route.remove()}
        />
      </div>
      {!route.folded && (
        <div className={styles.body}>
          <RouteMap overlay={props.overlay} />
          <Textarea
            placeholder="Notes for this route..."
            resize="vertical"
            value={route.notes}
            textarea={{ className: styles.notes_area }}
            onChange={(_event, data) => { route.notes = data.value; }}
            onBlur={() => route.commit()}
          />
        </div>
      )}
    </Card>
  );
}
