import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent as ReactDragEvent,
  type Dispatch,
  type SetStateAction,
} from "react";
import {
  Button,
  makeStyles,
  mergeClasses,
  tokens,
} from "@fluentui/react-components";
import api from "./api";
import { RouteCard, type RouteStats } from "./route-card";
import type { MapOverlay, TrackPoint } from "./route-map";
import { TripCard } from "./trip-card";

const use_styles = makeStyles({
  content: {
    flex: "1 1 auto",
    /* Keep the document at least this wide so the assistant panel can never be
     * dragged over it: at the smallest window (600px) each gets half.
     */
    minWidth: "300px",
    minHeight: 0,
    overflowY: "auto",
    padding: "12px",
    /* Contain Leaflet's internal z-index (panes and controls reach ~1000) in a
     * private stacking context so the map cannot paint over sibling UI.
     */
    isolation: "isolate",
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
  route_wrap: {
    position: "relative",
  },
  dragging: {
    opacity: 0.5,
  },
  drop_before: {
    "::before": {
      content: '""',
      position: "absolute",
      left: 0,
      right: 0,
      top: "-6px",
      height: "2px",
      background: tokens.colorBrandStroke1,
      borderRadius: "2px",
    },
  },
  drop_after_last: {
    "::after": {
      content: '""',
      position: "absolute",
      left: 0,
      right: 0,
      bottom: "-6px",
      height: "2px",
      background: tokens.colorBrandStroke1,
      borderRadius: "2px",
    },
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
  stats: RouteStats | null;
  route_loading: boolean;
}

type CardView = TripCardView | RouteCardView;

/* Tracks live apart from the cards, keyed by route id, so a map can be handed
 * the whole trip while a card only carries its description.
 */
type RouteTracks = Record<string, TrackPoint[]>;

/* Shared stand-ins for a route the tracks do not cover. A fresh literal per
 * render would look like new data to the map and profile effects below.
 */
const EMPTY_TRACK: TrackPoint[] = [];
const EMPTY_OVERLAY: MapOverlay = { polylines: [], markers: [], fit: null };

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
  #overlays: Record<string, MapOverlay>;
  #on_title_change: (title: string) => void;

  constructor(on_title_change: (title: string) => void) {
    [this.#cards, this.#set_cards] = useState<CardView[]>([]);
    [this.#tracks, this.#set_tracks] = useState<RouteTracks>({});
    /* RouteMap refits its bounds whenever the overlay it is given changes, so
     * building one per render would throw away the user's pan and zoom on
     * every keystroke. Cache them until a track actually moves.
     */
    const tracks = this.#tracks;
    this.#overlays = useMemo(() => Object.fromEntries(
      Object.keys(tracks).map((id) => [id, route_overlay(id, tracks)])
    ), [tracks]);
    this.#on_title_change = on_title_change;
  }

  get cards(): CardView[] {
    return this.#cards;
  }

  set cards(cards: CardView[]) {
    this.#set_cards(cards);
  }

  overlay(route_id: string): MapOverlay {
    return this.#overlays[route_id] ?? EMPTY_OVERLAY;
  }

  track(route_id: string): TrackPoint[] {
    return this.#tracks[route_id] ?? EMPTY_TRACK;
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

  set_trip_card(title: string, notes: string): void {
    this.#set_cards((cards) => cards.map((card) =>
      card.kind === "trip" ? { ...card, title, notes } : card
    ));
    this.title = title;
  }

  set_route_card(id: string, title: string, notes: string): void {
    this.#set_cards((cards) => cards.map((card) =>
      card.id === id && card.kind === "route"
        ? { ...card, title, notes }
        : card
    ));
  }

  add_route_card(
    id: string,
    title: string,
    notes: string,
    track: TrackPoint[],
    stats: RouteStats | null,
  ): void {
    this.#set_cards((cards) => [
      ...cards, { id, kind: "route", title, notes, stats, route_loading: false }
    ]);
    this.#set_tracks((tracks) => ({ ...tracks, [id]: track }));
  }

  /* Toggle the route header spinner. The backend turns it on while it loads
   * route details in the background (points of interest) and off once loading
   * finishes.
   */
  set_route_loading(id: string, loading: boolean): void {
    this.#set_cards((cards) => cards.map((card) =>
      card.id === id && card.kind === "route"
        ? { ...card, route_loading: loading }
        : card
    ));
  }

  remove_card(id: string): void {
    this.#set_cards((cards) => cards.filter((card) => card.id !== id));
    this.#set_tracks((tracks) => {
      const next = { ...tracks };
      delete next[id];
      return next;
    });
  }

  /* Reorder a route card to sit just after after_id, or at the front of the
   * route list when after_id is null. The trip card always leads, so a front
   * drop lands right below it. Non-route ids and unknown targets are ignored,
   * mirroring the model, so a stale drop cannot scramble the list.
   */
  move_card(id: string, after_id: string | null): void {
    this.#set_cards((cards) => {
      const moving = cards.find((card) => card.id === id);
      if (moving === undefined || moving.kind !== "route")
        return cards;
      const rest = cards.filter((card) => card.id !== id);
      if (after_id === null) {
        const at = rest.findIndex((card) => card.kind === "route");
        const cut = at === -1 ? rest.length : at;
        return [...rest.slice(0, cut), moving, ...rest.slice(cut)];
      }
      const at = rest.findIndex((card) => card.id === after_id);
      if (at === -1)
        return cards;
      return [...rest.slice(0, at + 1), moving, ...rest.slice(at + 1)];
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

  /* Drag-to-reorder state. grip_armed gates which card the browser may lift:
   * a card is only draggable once its grip is pressed, so pointer drags that
   * start inside a text field never move the card. drag_id is the card in
   * flight; drop_after is where it would land (null = front of the routes).
   */
  const grip_armed = useRef<string | null>(null);
  const [drag_id, set_drag_id] = useState<string | null>(null);
  const [drop_after, set_drop_after] = useState<string | null>(null);

  useEffect(() => {
    window.doc = doc;
    return () => { window.doc = null; };
  });

  const route_ids = doc.cards
    .filter((card) => card.kind === "route")
    .map((card) => card.id);
  const last_route = route_ids[route_ids.length - 1] ?? null;

  function end_drag(): void {
    grip_armed.current = null;
    set_drag_id(null);
    set_drop_after(null);
  }

  function on_drag_start(
    event: ReactDragEvent<HTMLDivElement>, id: string,
  ): void {
    if (grip_armed.current !== id) {
      event.preventDefault();
      return;
    }
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", id);
    set_drag_id(id);
    set_drop_after(null);
  }

  function on_drag_over(
    event: ReactDragEvent<HTMLDivElement>, over_id: string,
  ): void {
    if (drag_id === null)
      return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    const rect = event.currentTarget.getBoundingClientRect();
    const before = event.clientY < rect.top + rect.height / 2;
    const at = route_ids.indexOf(over_id);
    set_drop_after(before ? (at <= 0 ? null : route_ids[at - 1]!) : over_id);
  }

  function on_drop(event: ReactDragEvent<HTMLDivElement>): void {
    if (drag_id === null)
      return;
    event.preventDefault();
    const from = route_ids.indexOf(drag_id);
    const pred = from > 0 ? route_ids[from - 1]! : null;
    if (drop_after !== drag_id && drop_after !== pred) {
      doc.move_card(drag_id, drop_after);
      void api.move_route(drag_id, drop_after);
    }
    end_drag();
  }

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
                  on_change={(title, notes) => doc.set_trip_card(title, notes)}
                />
              );
            case "route": {
              const ri = route_ids.indexOf(card.id);
              const line_before = drag_id !== null && (
                ri === 0 ? drop_after === null : drop_after === route_ids[ri - 1]
              );
              const line_after_last = drag_id !== null &&
                card.id === last_route && drop_after === card.id;
              return (
                <div
                  key={card.id}
                  className={mergeClasses(
                    styles.route_wrap,
                    card.id === drag_id && styles.dragging,
                    line_before && styles.drop_before,
                    line_after_last && styles.drop_after_last,
                  )}
                  draggable
                  onDragStart={(event) => on_drag_start(event, card.id)}
                  onDragOver={(event) => on_drag_over(event, card.id)}
                  onDrop={on_drop}
                  onDragEnd={end_drag}
                >
                  <RouteCard
                    id={card.id}
                    title={card.title}
                    notes={card.notes}
                    stats={card.stats}
                    track={doc.track(card.id)}
                    overlay={doc.overlay(card.id)}
                    route_loading={card.route_loading}
                    on_remove={(id) => doc.remove_card(id)}
                    on_grip_down={() => { grip_armed.current = card.id; }}
                    on_grip_up={() => { grip_armed.current = null; }}
                  />
                </div>
              );
            }
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
