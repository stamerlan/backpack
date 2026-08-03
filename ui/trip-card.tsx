import { useState, type Dispatch, type SetStateAction } from "react";
import {
  Card,
  Input,
  makeStyles,
  tokens,
} from "@fluentui/react-components";
import api from "./api";
import { MdInput } from "./md-input";

const use_styles = makeStyles({
  card: {
    display: "flex",
    flexDirection: "column",
    gap: "12px",
    padding: "16px",
  },
  title_root: {
    border: "none",
    borderRadius: 0,
    paddingLeft: 0,
    paddingRight: 0,
    backgroundColor: "transparent",
    "::after": { display: "none" },
    "::before": { display: "none" },
  },
  title_input: {
    paddingLeft: 0,
    paddingRight: 0,
    fontFamily: tokens.fontFamilyBase,
    fontSize: tokens.fontSizeHero800,
    lineHeight: tokens.lineHeightHero800,
    fontWeight: tokens.fontWeightSemibold,
  },
});

class TripView {
  #id: string;
  #title: string;
  #set_title: Dispatch<SetStateAction<string>>;
  #notes: string;
  #set_notes: Dispatch<SetStateAction<string>>;
  #on_title_change: (title: string) => void;

  constructor(
    id: string,
    title: string,
    notes: string,
    on_title_change: (title: string) => void,
  ) {
    this.#id = id;
    [this.#title, this.#set_title] = useState(title);
    [this.#notes, this.#set_notes] = useState(notes);
    this.#on_title_change = on_title_change;
  }

  get title(): string {
    return this.#title;
  }

  set title(title: string) {
    this.#set_title(title);
    this.#on_title_change(title);
  }

  get notes(): string {
    return this.#notes;
  }

  set notes(notes: string) {
    this.#set_notes(notes);
  }

  commit(): void {
    void api.set_trip_info(this.#id, this.#title, this.#notes);
  }
}

export function TripCard(props: {
  id: string;
  title: string;
  notes: string;
  on_title_change: (title: string) => void;
}) {
  const styles = use_styles();
  const trip = new TripView(
    props.id, props.title, props.notes, props.on_title_change
  );

  return (
    <Card className={styles.card}>
      <Input
        className={styles.title_root}
        appearance="underline"
        placeholder="Untitled trip"
        value={trip.title}
        input={{ className: styles.title_input }}
        onChange={(_event, data) => { trip.title = data.value; }}
        onBlur={() => trip.commit()}
      />
      <MdInput
        placeholder="Add trip notes..."
        value={trip.notes}
        min_height={160}
        on_change={(value) => { trip.notes = value; }}
        on_commit={() => trip.commit()}
      />
    </Card>
  );
}
