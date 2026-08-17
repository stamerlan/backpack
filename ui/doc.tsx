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
 *
 * Reordering runs through dnd-kit: a DndContext with pointer, touch and
 * keyboard sensors wraps a vertical SortableContext of the route cards, so a
 * drag started from a card's grip works the same on a mouse or a finger and
 * auto-scrolls the document when it reaches an edge.
 */
import {
  useEffect,
  useMemo,
  useState,
  type ButtonHTMLAttributes,
} from "react";
import { Button, mergeClasses } from "@fluentui/react-components";
import { useTranslation } from "react-i18next";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  closestCenter,
  pointerWithin,
  useSensor,
  useSensors,
  type CollisionDetection,
  type DragEndEvent,
} from "@dnd-kit/core";
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
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

/* Reorder the moment the pointer moves into a neighbour card, instead of
 * waiting for the lifted card's centre to pass theirs, so a tall expanded
 * card no longer needs a long drag to trade places with a folded one.
 * closestCenter is the fallback for the gaps and the instants the pointer
 * sits over no card, so the drop target never goes blank mid-drag.
 */
const track_pointer: CollisionDetection = (args) => {
  const hits = pointerWithin(args);
  return hits.length > 0 ? hits : closestCenter(args);
};

/* One route card as a sortable item. useSortable must run in a component of
 * its own since it is a hook, so this holds the drag wiring the document map
 * cannot: the grip becomes the drag activator, and the wrapper carries the
 * transform dnd-kit uses to slide siblings apart while a card is in flight.
 */
function SortableRoute(props: {
  card: RouteCardView;
  track: TrackPoint[];
  overlay: MapOverlay;
  on_change: (title: string, notes: string) => void;
  on_remove: (id: string) => void;
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    setActivatorNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: props.card.id });
  /* Translate only, never the scaleX/scaleY dnd-kit also packs into the
   * transform: with folded and expanded cards differing in height, scaling
   * would squash the lifted card to the size of whichever card it hovers.
   */
  const style = {
    transform: CSS.Translate.toString(transform),
    transition,
  };
  return (
    <div
      ref={setNodeRef}
      style={style}
      className={mergeClasses("doc-route", isDragging && "dragging")}
    >
      <RouteCard
        id={props.card.id}
        title={props.card.title}
        notes={props.card.notes}
        stats={props.card.stats}
        track={props.track}
        overlay={props.overlay}
        route_loading={props.card.route_loading}
        on_change={props.on_change}
        on_remove={props.on_remove}
        grip_ref={setActivatorNodeRef}
        grip_props={{ ...attributes, ...listeners } as
          ButtonHTMLAttributes<HTMLButtonElement>}
      />
    </div>
  );
}

export function Doc(props: {
  on_title_change: (title: string) => void;
}) {
  const { t } = useTranslation();
  const [cards, set_cards] = useState<CardView[]>([]);
  const [tracks, set_tracks] = useState<RouteTracks>({});

  /* A small distance gate lets a plain tap on the grip fall through as a
   * click, so a drag only starts once the pointer or finger actually moves.
   * The keyboard sensor makes the grip reorder with the arrow keys too.
   */
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 5 } }),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    }),
  );

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

  /* Reorder on drop, then translate the sortable's new neighbour list back
   * into the backend's after_id contract: the id the card now trails, or
   * null when it leads the routes.
   */
  function on_drag_end(event: DragEndEvent): void {
    const { active, over } = event;
    if (over === null || active.id === over.id)
      return;
    const from = route_ids.indexOf(String(active.id));
    const to = route_ids.indexOf(String(over.id));
    if (from === -1 || to === -1)
      return;
    const ordered = arrayMove(route_ids, from, to);
    const at = ordered.indexOf(String(active.id));
    const after_id = at === 0 ? null : ordered[at - 1]!;
    doc.move_card(String(active.id), after_id);
    void api.move_route(String(active.id), after_id);
  }

  return (
    <main className="doc-content">
      <DndContext
        sensors={sensors}
        collisionDetection={track_pointer}
        onDragEnd={on_drag_end}
      >
        <div className="doc-stack">
          <SortableContext
            items={route_ids}
            strategy={verticalListSortingStrategy}
          >
            {cards.map((card) => {
              switch (card.kind) {
                case "trip":
                  return (
                    <TripCard
                      key={card.id}
                      id={card.id}
                      title={card.title}
                      notes={card.notes}
                      on_change={(title, notes) =>
                        doc.set_trip_card(title, notes)}
                    />
                  );
                case "route":
                  return (
                    <SortableRoute
                      key={card.id}
                      card={card}
                      track={tracks[card.id] ?? EMPTY_TRACK}
                      overlay={overlays[card.id] ?? EMPTY_OVERLAY}
                      on_change={(title, notes) =>
                        doc.set_route_card(card.id, title, notes)}
                      on_remove={(id) => doc.remove_card(id)}
                    />
                  );
                default:
                  return null;
              }
            })}
          </SortableContext>
          <Button
            className="doc-add-route"
            onClick={() => { void api.add_route(); }}
          >
            + {t("doc.add_route")}
          </Button>
        </div>
      </DndContext>
    </main>
  );
}
