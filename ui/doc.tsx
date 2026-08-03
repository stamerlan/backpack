import {
  useEffect,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import { Button, makeStyles } from "@fluentui/react-components";
import api from "./api";
import { RouteCard } from "./route-card";
import { TripCard } from "./trip-card";

const use_styles = makeStyles({
  content: {
    flex: "1 1 auto",
    minHeight: 0,
    overflowY: "auto",
    padding: "12px",
  },
  stack: {
    display: "flex",
    flexDirection: "column",
    gap: "12px",
    maxWidth: "800px",
    margin: "0 auto",
  },
  add_route: {
    alignSelf: "flex-start",
  },
});

interface TripCardView {
  id: string;
  kind: "trip";
  title: string;
  notes: string;
}

interface RouteCardView {
  id: string;
  kind: "route";
  title: string;
  notes: string;
}

type CardView = TripCardView | RouteCardView;

/* The document view's state together with the whole surface the backend may
 * drive. It is a hook-backed view model: the constructor calls useState, so a
 * fresh instance is built on every render holding the current cards and a live
 * setter. The document title lives in the app bar, so here it is a write-only
 * channel; taking the callback in the constructor keeps it current without a
 * separate bind step.
 */
class DocView {
  #cards: CardView[];
  #set_cards: Dispatch<SetStateAction<CardView[]>>;
  #on_title_change: (title: string) => void;

  constructor(on_title_change: (title: string) => void) {
    [this.#cards, this.#set_cards] = useState<CardView[]>([]);
    this.#on_title_change = on_title_change;
  }

  get cards(): CardView[] {
    return this.#cards;
  }

  set cards(cards: CardView[]) {
    this.#set_cards(cards);
  }

  set title(title: string) {
    this.#on_title_change(title);
  }

  clear(): void {
    this.#set_cards([]);
    this.title = "";
  }

  add_trip_card(id: string, title: string, notes: string): void {
    this.#set_cards((cards) => [...cards, { id, kind: "trip", title, notes }]);
    this.title = title;
  }

  add_route_card(id: string, title: string, notes: string): void {
    this.#set_cards((cards) => [...cards, { id, kind: "route", title, notes }]);
  }

  remove_card(id: string): void {
    this.#set_cards((cards) => cards.filter((card) => card.id !== id));
  }
}

/* One DocView instance is the document view's whole backend surface: while
 * mounted it is published as the global `doc`, so the backend pushes changes
 * with doc.add_route_card(...), doc.clear() and the like.
 */
export function Doc(props: {
  on_title_change: (title: string) => void;
}) {
  const styles = use_styles();
  const doc = new DocView(props.on_title_change);

  useEffect(() => {
    window.doc = doc;
    return () => { window.doc = null; };
  });

  return (
    <main className={styles.content}>
      <div className={styles.stack}>
        {doc.cards.map((card) => {
          switch (card.kind) {
            case "trip":
              return (
                <TripCard
                  key={card.id}
                  id={card.id}
                  title={card.title}
                  notes={card.notes}
                  on_title_change={props.on_title_change}
                />
              );
            case "route":
              return (
                <RouteCard
                  key={card.id}
                  id={card.id}
                  title={card.title}
                  notes={card.notes}
                  on_remove={(id) => doc.remove_card(id)}
                />
              );
            default:
              return null;
          }
        })}
        <Button
          className={styles.add_route}
          appearance="subtle"
          onClick={() => { void api.add_route(); }}
        >
          + Add route
        </Button>
      </div>
    </main>
  );
}

declare global {
  interface Window {
    doc: DocView | null;
  }
}

window.doc = null;
