/* A Leaflet map showing one route in the context of its trip. Leaflet owns
 * everything inside the host element, so the map is built once on mount and
 * driven imperatively after that; route-map.css paints the layers from
 * Fluent tokens.
 *
 * Properties:
 *   - overlay: The lines and markers to draw, and the bounds to frame.
 *   - hover: Point to echo as a dot, following the profile chart's cursor.
 *
 * State:
 *   - height: Map height in pixels, set by dragging the handle below it.
 *   - ctl: The Leaflet handles, in a ref rather than state because React
 *     never renders them and must not re-render when they change.
 */
import {
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import * as leaflet from "leaflet";
import "leaflet/dist/leaflet.css";
import "./route-map.css";

/* Base maps for the layer switcher; the first entry is the default. Every
 * layer shares MAX_ZOOM and declares its own native zoom, so Leaflet upscale
 * instead of blanking out when a provider runs out of levels.
 */
const MAP_LAYERS = [
  {
    id: "opentopo",
    label: "OpenTopoMap",
    url: "https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
    attribution:
      "Map data: (C) OpenStreetMap contributors, SRTM | " +
      "Map style: (C) OpenTopoMap (CC-BY-SA)",
    native_zoom: 17,
  },
  {
    id: "osm",
    label: "OpenStreetMap",
    url: "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: "(C) OpenStreetMap contributors",
    native_zoom: 19,
  },
  {
    id: "cyclosm",
    label: "CyclOSM",
    url:
      "https://{s}.tile-cyclosm.openstreetmap.fr/cyclosm/" +
      "{z}/{x}/{y}.png",
    attribution: "CyclOSM | (C) OpenStreetMap contributors",
    native_zoom: 20,
  },
  {
    id: "satellite",
    label: "Satellite",
    url:
      "https://server.arcgisonline.com/ArcGIS/rest/services/" +
      "World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "Tiles (C) Esri, Maxar, Earthstar Geographics",
    native_zoom: 19,
  },
];
const MAX_ZOOM = 19;

/* Default height and the drag-resize clamps, in px. */
const DEFAULT_H = 320;
const MIN_H = 160;
const MAX_H = 900;

const MARKER_RADIUS = 6;
const MARKER_WEIGHT = 2;

export interface Coord {
  lat: number;
  long: number;
}

export interface TrackPoint extends Coord {
  elev_m: number;
  slope: number;
  dist_m: number;   /* distance from route start, meters */
  dur_s: number;    /* estimated time from route start, seconds */
}

export interface MapPolyline {
  points: Coord[];
  className: string;
  weight: number;
}

export interface MapMarker {
  point: Coord;
  className: string;
}

export interface MapOverlay {
  polylines: MapPolyline[];
  markers: MapMarker[];
  fit: Coord[] | null;   /* bounds to frame, or null to leave the view alone */
}

/* The live map, built together on mount and torn down together. */
interface MapCtl {
  map: leaflet.Map;
  routes: leaflet.LayerGroup;   /* the trip's lines and end dots */
  hover: leaflet.LayerGroup;    /* the dot echoing the profile cursor */
  destroy(): void;
}

function to_coords(point: Coord): leaflet.LatLngTuple {
  return [point.lat, point.long];
}

function create_map(host: HTMLDivElement): MapCtl {
  const map = leaflet.map(host, {
    scrollWheelZoom: false,
    doubleClickZoom: false,
    keyboard: false,
  });
  map.setView([20, 0], 2);

  const choices: Record<string, leaflet.Layer> = {};
  MAP_LAYERS.forEach((spec, index) => {
    const tiles = leaflet.tileLayer(spec.url, {
      attribution: spec.attribution,
      maxZoom: MAX_ZOOM,
      maxNativeZoom: spec.native_zoom,
    });
    if (index === 0)
      tiles.addTo(map);
    choices[spec.label] = tiles;
  });
  leaflet.control.layers(choices).addTo(map);
  map.attributionControl.setPrefix(false);

  const container = map.getContainer();

  /* Keep the map and its controls out of the Tab order. */
  container
    .querySelectorAll("a, input")
    .forEach((node) => { (node as HTMLElement).tabIndex = -1; });

  /* Ctrl + wheel zooms; a bare wheel keeps scrolling the document. */
  const on_wheel = (event: WheelEvent): void => {
    if (!event.ctrlKey)
      return;
    event.preventDefault();
    const dir = event.deltaY < 0 ? 1 : -1;
    const around = map.mouseEventToLatLng(event);
    map.setZoomAround(around, map.getZoom() + dir);
  };
  container.addEventListener("wheel", on_wheel, { passive: false });

  return {
    map,
    routes: leaflet.layerGroup().addTo(map),
    hover: leaflet.layerGroup().addTo(map),
    destroy() {
      container.removeEventListener("wheel", on_wheel);
      map.remove();
    },
  };
}

function paint(ctl: MapCtl, overlay: MapOverlay): void {
  ctl.routes.clearLayers();
  for (const line of overlay.polylines)
    leaflet.polyline(line.points.map(to_coords), {
      weight: line.weight, className: line.className, interactive: false,
    }).addTo(ctl.routes);
  for (const marker of overlay.markers)
    leaflet.circleMarker(to_coords(marker.point), {
      radius: MARKER_RADIUS, weight: MARKER_WEIGHT, fillOpacity: 1,
      className: marker.className, interactive: false,
    }).addTo(ctl.routes);

  if (overlay.fit !== null && overlay.fit.length > 0)
    ctl.map.fitBounds(overlay.fit.map(to_coords), {
      animate: false, padding: [20, 20],
    });
}

function put_hover(ctl: MapCtl, point: Coord | null): void {
  ctl.hover.clearLayers();
  if (point === null)
    return;
  leaflet.circleMarker(to_coords(point), {
    radius: MARKER_RADIUS, weight: MARKER_WEIGHT, fillOpacity: 1,
    className: "route-map-hover", interactive: false,
  }).addTo(ctl.hover);
}

export function RouteMap(props: {
  overlay: MapOverlay;
  hover?: Coord | null;
}) {
  const host = useRef<HTMLDivElement>(null);
  const ctl = useRef<MapCtl | null>(null);
  const [height, set_height] = useState(DEFAULT_H);

  useEffect(() => {
    /* A host with no height yet cannot hold a map, and a folded card never
     * gets one until it is opened again and this component remounts.
     */
    if (host.current === null || host.current.clientHeight === 0)
      return;
    const created = create_map(host.current);
    ctl.current = created;
    return () => {
      created.destroy();
      ctl.current = null;
    };
  }, []);

  useEffect(() => {
    if (ctl.current !== null)
      paint(ctl.current, props.overlay);
  }, [props.overlay]);

  useEffect(() => {
    if (ctl.current !== null)
      put_hover(ctl.current, props.hover ?? null);
  }, [props.hover]);

  useEffect(() => {
    ctl.current?.map.invalidateSize(false);
  }, [height]);

  function start_resize(event: ReactPointerEvent<HTMLDivElement>): void {
    event.preventDefault();
    const handle = event.currentTarget;
    handle.setPointerCapture(event.pointerId);
    const start_y = event.clientY;
    const start_h = height;

    const on_move = (move: PointerEvent): void => {
      const next = start_h + move.clientY - start_y;
      set_height(Math.min(Math.max(next, MIN_H), MAX_H));
    };
    const on_up = (): void => {
      handle.releasePointerCapture(event.pointerId);
      handle.removeEventListener("pointermove", on_move);
      handle.removeEventListener("pointerup", on_up);
      handle.removeEventListener("pointercancel", on_up);
    };
    handle.addEventListener("pointermove", on_move);
    handle.addEventListener("pointerup", on_up);
    handle.addEventListener("pointercancel", on_up);
  }

  return (
    <div className="route-map-block">
      <div ref={host} className="route-map" style={{ height }} />
      <div
        className="route-map-handle"
        title="Drag to resize"
        onPointerDown={start_resize}
      />
    </div>
  );
}
