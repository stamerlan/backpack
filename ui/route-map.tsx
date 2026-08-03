import {
  useEffect,
  useRef,
  useState,
  type Dispatch,
  type PointerEvent,
  type RefObject,
  type SetStateAction,
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

class MapView {
  #host: RefObject<HTMLDivElement | null>;
  #map: RefObject<leaflet.Map | null>;
  #layer: RefObject<leaflet.LayerGroup | null>;
  #hover: RefObject<leaflet.LayerGroup | null>;
  #height: number;
  #set_height: Dispatch<SetStateAction<number>>;

  constructor() {
    this.#host = useRef<HTMLDivElement>(null);
    this.#map = useRef<leaflet.Map | null>(null);
    this.#layer = useRef<leaflet.LayerGroup | null>(null);
    this.#hover = useRef<leaflet.LayerGroup | null>(null);
    [this.#height, this.#set_height] = useState(DEFAULT_H);
  }

  get host(): RefObject<HTMLDivElement | null> {
    return this.#host;
  }

  get height(): number {
    return this.#height;
  }

  mount(): () => void {
    if (this.#host.current === null || this.#host.current.clientHeight === 0)
      return () => {};

    const map = leaflet.map(this.#host.current, {
      scrollWheelZoom: false,
      doubleClickZoom: false,
      keyboard: false,
    });
    this.#map.current = map;
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
    this.#layer.current = leaflet.layerGroup().addTo(map);

    this.#hover.current = leaflet.layerGroup().addTo(map);

    /* Keep the map and its controls out of the Tab order. */
    map
      .getContainer()
      .querySelectorAll("a, input")
      .forEach((node) => { (node as HTMLElement).tabIndex = -1; });

    /* Ctrl + wheel zooms; a bare wheel keeps scrolling the document. */
    const container = map.getContainer();
    const on_wheel = (event: WheelEvent): void => {
      if (!event.ctrlKey)
        return;
      event.preventDefault();
      const dir = event.deltaY < 0 ? 1 : -1;
      const around = map.mouseEventToLatLng(event);
      map.setZoomAround(around, map.getZoom() + dir);
    };
    container.addEventListener("wheel", on_wheel, { passive: false });

    return () => {
      container.removeEventListener("wheel", on_wheel);
      map.remove();
      this.#map.current = null;
      this.#layer.current = null;
      this.#hover.current = null;
    };
  }

  paint(overlay: MapOverlay): void {
    if (this.#map.current === null || this.#layer.current === null)
      return;

    const to_coords = (point: Coord): leaflet.LatLngTuple => {
      return [point.lat, point.long];
    }

    this.#layer.current.clearLayers();
    for (const line of overlay.polylines)
      leaflet.polyline(line.points.map(to_coords), {
        weight: line.weight, className: line.className, interactive: false,
      }).addTo(this.#layer.current);
    for (const marker of overlay.markers)
      leaflet.circleMarker(to_coords(marker.point), {
        radius: MARKER_RADIUS, weight: MARKER_WEIGHT, fillOpacity: 1,
        className: marker.className, interactive: false,
      }).addTo(this.#layer.current);

    if (overlay.fit !== null && overlay.fit.length > 0)
      this.#map.current.fitBounds(overlay.fit.map(to_coords), {
        animate: false, padding: [20, 20],
      });
  }

  put_hover(point: Coord | null): void {
    const layer = this.#hover.current;
    if (layer === null)
      return;
    layer.clearLayers();
    if (point === null)
      return;
    leaflet.circleMarker([point.lat, point.long], {
      radius: MARKER_RADIUS, weight: MARKER_WEIGHT, fillOpacity: 1,
      className: "route-map-hover", interactive: false,
    }).addTo(layer);
  }

  invalidate(): void {
    this.#map.current?.invalidateSize(false);
  }

  start_resize(event: PointerEvent<HTMLDivElement>): void {
    event.preventDefault();
    const handle = event.currentTarget;
    handle.setPointerCapture(event.pointerId);
    const start_y = event.clientY;
    const start_h = this.#height;

    const on_move = (move: globalThis.PointerEvent): void => {
      const next = start_h + move.clientY - start_y;
      this.#set_height(Math.min(Math.max(next, MIN_H), MAX_H));
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
}

export function RouteMap(props: {
  overlay: MapOverlay;
  hover?: Coord | null;
}) {
  const map = new MapView();

  useEffect(() => map.mount(), []);
  useEffect(() => { map.paint(props.overlay); }, [props.overlay]);
  useEffect(() => { map.put_hover(props.hover ?? null); }, [props.hover]);
  useEffect(() => { map.invalidate(); }, [map.height]);

  return (
    <div className="route-map-block">
      <div ref={map.host} className="route-map" style={{ height: map.height }} />
      <div
        className="route-map-handle"
        title="Drag to resize"
        onPointerDown={(event) => map.start_resize(event)}
      />
    </div>
  );
}
