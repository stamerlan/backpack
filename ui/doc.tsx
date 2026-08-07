/* The trip document: a scrolling stack of cards, the trip card first and one
 * route card per leg below it. While mounted the view publishes itself as
 * window.doc, the surface the backend pushes every change through, so the
 * methods below mirror UI in src/backpack/ui.py.
 *
 * Properties:
 *   - on_title_change: Reports the trip title so the app bar can show it.
 *
 * State:
 *   - cards: The trip card and the route cards, in display order.
 *   - tracks: Sampled points per route id, held apart from the cards so
 *     every map can draw the whole trip rather than just its own leg.
 *   - drag_id: Route card being dragged, null when nothing is in flight.
 *   - drop_after: Route the dragged card would land after, null for first.
 *   - grip_armed: Card whose grip is held. Only that card may be lifted, so
 *     a pointer drag starting in a text field never moves anything.
 */
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type DragEvent as ReactDragEvent,
} from "react";
import { Button, mergeClasses } from "@fluentui/react-components";
import api from "./api";
import { RouteCard, type RouteStats } from "./route-card";
import type { MapOverlay, TrackPoint } from "./route-map";
import { TripCard } from "./trip-card";
import "./doc.css";

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

type RouteTracks = Record<string, TrackPoint[]>;

/* Everything the backend may call on window.doc. */
export interface DocApi {
  clear(): void;
  add_trip_card(id: string, title: string, notes: string): void;
  set_trip_card(title: string, notes: string): void;
  set_route_card(id: string, title: string, notes: string): void;
  add_route_card(
    id: string,
    title: string,
    notes: string,
    track: TrackPoint[],
    stats: RouteStats | null,
  ): void;
  /* Toggle the route header spinner. The backend turns it on while it loads
   * route details in the background (points of interest) and off once
   * loading finishes.
   */
  set_route_loading(id: string, loading: boolean): void;
  remove_card(id: string): void;
  /* Reorder a route card to sit just after after_id, or at the front of the
   * route list when after_id is null. The trip card always leads, so a front
   * drop lands right below it. Non-route ids and unknown targets are ignored,
   * mirroring the model, so a stale drop cannot scramble the list.
   */
  move_card(id: string, after_id: string | null): void;
}

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

export function Doc(props: {
  on_title_change: (title: string) => void;
}) {
  const [cards, set_cards] = useState<CardView[]>([]);
  const [tracks, set_tracks] = useState<RouteTracks>({});
  const grip_armed = useRef<string | null>(null);
  const [drag_id, set_drag_id] = useState<string | null>(null);
  const [drop_after, set_drop_after] = useState<string | null>(null);

  /* Built once: the state setters it closes over never change identity, so
   * the backend always reaches the live document through the same object.
   */
  const doc = useMemo<DocApi>(() => ({
    clear() {
      set_cards([]);
      set_tracks({});
    },
    add_trip_card(id, title, notes) {
      set_cards((all) => [...all, { id, kind: "trip", title, notes }]);
    },
    set_trip_card(title, notes) {
      set_cards((all) => all.map((card) =>
        card.kind === "trip" ? { ...card, title, notes } : card
      ));
    },
    set_route_card(id, title, notes) {
      set_cards((all) => all.map((card) =>
        card.id === id && card.kind === "route"
          ? { ...card, title, notes }
          : card
      ));
    },
    add_route_card(id, title, notes, track, stats) {
      set_cards((all) => [
        ...all,
        { id, kind: "route", title, notes, stats, route_loading: false },
      ]);
      set_tracks((all) => ({ ...all, [id]: track }));
    },
    set_route_loading(id, loading) {
      set_cards((all) => all.map((card) =>
        card.id === id && card.kind === "route"
          ? { ...card, route_loading: loading }
          : card
      ));
    },
    remove_card(id) {
      set_cards((all) => all.filter((card) => card.id !== id));
      set_tracks((all) => {
        const { [id]: _removed, ...rest } = all;
        return rest;
      });
    },
    move_card(id, after_id) {
      set_cards((all) => {
        const moving = all.find((card) => card.id === id);
        if (moving === undefined || moving.kind !== "route")
          return all;
        const rest = all.filter((card) => card.id !== id);
        if (after_id === null) {
          const at = rest.findIndex((card) => card.kind === "route");
          const cut = at === -1 ? rest.length : at;
          return [...rest.slice(0, cut), moving, ...rest.slice(cut)];
        }
        const at = rest.findIndex((card) => card.id === after_id);
        if (at === -1)
          return all;
        return [...rest.slice(0, at + 1), moving, ...rest.slice(at + 1)];
      });
    },
  }), []);

  useEffect(() => {
    window.doc = doc;
    return () => { window.doc = null; };
  }, [doc]);

  /* The app bar shows whatever the trip card holds, so read it back out of
   * the cards instead of announcing it from each mutator.
   */
  const { on_title_change } = props;
  const trip_title =
    cards.find((card) => card.kind === "trip")?.title ?? "";
  useEffect(() => {
    on_title_change(trip_title);
  }, [on_title_change, trip_title]);

  /* RouteMap refits its bounds whenever the overlay it is given changes, so
   * building one per render would throw away the user's pan and zoom on every
   * keystroke. Cache them until a track actually moves.
   */
  const overlays = useMemo(() => Object.fromEntries(
    Object.keys(tracks).map((id) => [id, route_overlay(id, tracks)])
  ), [tracks]);

  const route_ids = cards
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
    <main className="doc-content">
      <div className="doc-stack">
        {cards.map((card) => {
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
              const before = ri === 0
                ? drop_after === null
                : drop_after === route_ids[ri - 1];
              return (
                <div
                  key={card.id}
                  className={mergeClasses(
                    "doc-route",
                    card.id === drag_id && "dragging",
                    drag_id !== null && before && "drop-before",
                    drag_id !== null && card.id === last_route &&
                      drop_after === card.id && "drop-after",
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
                    track={tracks[card.id] ?? EMPTY_TRACK}
                    overlay={overlays[card.id] ?? EMPTY_OVERLAY}
                    route_loading={card.route_loading}
                    on_change={(title, notes) =>
                      doc.set_route_card(card.id, title, notes)}
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
          className="doc-add-route"
          appearance="subtle"
          onClick={() => { void api.add_route(); }}
        >
          + Add route
        </Button>
      </div>
    </main>
  );
}