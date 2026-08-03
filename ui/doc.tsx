import {
  useEffect,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import { Button, makeStyles } from "@fluentui/react-components";
import api from "./api";
import { RouteCard } from "./route-card";
import type { MapOverlay, TrackPoint } from "./route-map";
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

/* Tracks live apart from the cards, keyed by route id, so a map can be handed
 * the whole trip while a card only carries its description.
 */
type RouteTracks = Record<string, TrackPoint[]>;

/* Turn one route and the trip's tracks into a map overlay. Every route map
 * shows the whole trip: the sibling routes as dim dashed context lines, then
 * this route's own track on top, colored and capped with start and end dots.
 * The class names key into route-map.css, which paints them from Fluent
 * tokens.
 */
function route_overlay(route_id: string, tracks: RouteTracks): MapOverlay {
  const overlay: MapOverlay = { polylines: [], markers: [], fit: null };

  /* Context first so the own route stacks on top. */
  for (const [id, track] of Object.entries(tracks)) {
    if (id === route_id || track.length === 0)
      continue;
    overlay.polylines.push(
      { points: track, className: "route-map-casing", weight: 9 },
      { points: track, className: "route-map-context", weight: 6 },
    );
    overlay.markers.push(
      { point: track[0]!, className: "route-map-context-dot" },
      { point: track[track.length - 1]!, className: "route-map-context-dot" },
    );
  }

  const own = tracks[route_id] ?? [];
  if (own.length === 0)
    return overlay;

  overlay.polylines.push(
    { points: own, className: "route-map-casing", weight: 9 },
    { points: own, className: "route-map-line", weight: 6 },
  );
  overlay.markers.push(
    { point: own[0]!, className: "route-map-start" },
    { point: own[own.length - 1]!, className: "route-map-end" },
  );
  overlay.fit = own;
  return overlay;
}

class DocView {
  #cards: CardView[];
  #set_cards: Dispatch<SetStateAction<CardView[]>>;
  #tracks: RouteTracks;
  #set_tracks: Dispatch<SetStateAction<RouteTracks>>;
  #on_title_change: (title: string) => void;

  constructor(on_title_change: (title: string) => void) {
    [this.#cards, this.#set_cards] = useState<CardView[]>([]);
    [this.#tracks, this.#set_tracks] = useState<RouteTracks>({});
    this.#on_title_change = on_title_change;
  }

  get cards(): CardView[] {
    return this.#cards;
  }

  set cards(cards: CardView[]) {
    this.#set_cards(cards);
  }

  overlay(route_id: string): MapOverlay {
    return route_overlay(route_id, this.#tracks);
  }

  track(route_id: string): TrackPoint[] {
    return this.#tracks[route_id] ?? [];
  }

  set title(title: string) {
    this.#on_title_change(title);
  }

  clear(): void {
    this.#set_cards([]);
    this.#set_tracks({});
    this.title = "";
  }

  add_trip_card(id: string, title: string, notes: string): void {
    this.#set_cards((cards) => [...cards, { id, kind: "trip", title, notes }]);
    this.title = title;
  }

  add_route_card(
    id: string, title: string, notes: string, track: TrackPoint[]
  ): void {
    this.#set_cards((cards) => [...cards, { id, kind: "route", title, notes }]);
    this.#set_tracks((tracks) => ({ ...tracks, [id]: track }));
  }

  remove_card(id: string): void {
    this.#set_cards((cards) => cards.filter((card) => card.id !== id));
    this.#set_tracks((tracks) => {
      const next = { ...tracks };
      delete next[id];
      return next;
    });
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
                  track={doc.track(card.id)}
                  overlay={doc.overlay(card.id)}
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
