import { useEffect, useRef, type RefObject } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import "./route-profile.css";
import type { TrackPoint } from "./route-map";

/* Fixed chart height, matching the map's minimum, in px. */
const PROFILE_H = 160;

function fmt_eta(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m`;
}

class ProfileView {
  #host: RefObject<HTMLDivElement | null>;
  #plot: RefObject<uPlot | null>;
  #track: RefObject<TrackPoint[]>;
  #data: RefObject<uPlot.AlignedData | null>;
  #width: RefObject<number>;
  #height: RefObject<number>;
  #on_hover: RefObject<(point: TrackPoint) => void>;
  #on_leave: RefObject<() => void>;

  constructor(
    on_hover: (point: TrackPoint) => void,
    on_leave: () => void,
  ) {
    this.#host = useRef<HTMLDivElement>(null);
    this.#plot = useRef<uPlot | null>(null);
    this.#track = useRef<TrackPoint[]>([]);
    this.#data = useRef<uPlot.AlignedData | null>(null);
    this.#width = useRef(0);
    this.#height = useRef(0);
    this.#on_hover = useRef(on_hover);
    this.#on_leave = useRef(on_leave);
    this.#on_hover.current = on_hover;
    this.#on_leave.current = on_leave;
  }

  get host(): RefObject<HTMLDivElement | null> {
    return this.#host;
  }

  mount(): () => void {
    const host = this.#host.current;
    if (host === null)
      return () => {};

    const observer = new ResizeObserver(() => this.#sync());
    observer.observe(host);

    return () => {
      observer.disconnect();
      this.#plot.current?.destroy();
      this.#plot.current = null;
    };
  }

  set_track(track: TrackPoint[]): void {
    this.#track.current = track;
    this.#data.current = [
      track.map((p) => p.dist_m / 1000),   /* x: km        */
      track.map((p) => p.elev_m),          /* elevation, m */
      track.map((p) => p.slope),           /* slope, %     */
    ];
    if (this.#plot.current)
      this.#plot.current.setData(this.#data.current);
    else
      requestAnimationFrame(() => this.#sync()); /* let layout settle */
  }

  /* The only place that sizes the plot: builds once, resizes after. */
  #sync(): void {
    const host = this.#host.current;
    if (host === null || this.#data.current === null)
      return;

    const w = Math.floor(host.clientWidth);
    const h = Math.floor(host.clientHeight);
    if (!w || !h) /* not laid out yet: a later observer tick retries */
      return;

    if (this.#plot.current === null) {
      this.#width.current = w;
      this.#height.current = h;
      this.#build(w, h);
      return;
    }
    if (w !== this.#width.current || h !== this.#height.current) {
      this.#width.current = w;
      this.#height.current = h;
      this.#plot.current.setSize({ width: w, height: h });
    }
  }

  #build(width: number, height: number): void {
    const host = this.#host.current;
    if (host === null || this.#data.current === null)
      return;

    const token = (name: string): string =>
      getComputedStyle(host).getPropertyValue(name).trim();
    const font_family =
      token("--fontFamilyBase") || "system-ui, sans-serif";

    const label_font = `11px ${font_family}`;
    const label_color = token("--colorNeutralForeground3"); /* subtle grey */
    const grid_color = token("--colorNeutralStroke2");
    const elev_color = token("--colorBrandStroke1");
    const slope_color = token("--colorPaletteGreenForeground1");
    const elev_fill =
      `color-mix(in srgb, ${elev_color} 15%, transparent)`;

    const opts: uPlot.Options = {
      width,
      height,
      padding: [12, 8, 0, 8],
      legend: { show: false },
      scales: { x: { time: false } },
      cursor: {
        x: true,
        y: false,
        points: { size: 7 },
        move: (u, left, top) => {
          if (left < 0) /* mouse leaving: let it go off */
            return [left, top];
          const idx = u.posToIdx(left); /* nearest sample */
          const snapped = u.valToPos(u.data[0]![idx]!, "x");
          return [snapped, top];
        },
      },
      axes: [
        {
          values: (_u, splits) => splits.map((km, idx, all) => {
            if (idx === 0)
              return `${km} m`;
            if (idx === all.length - 1)
              return `${km} km`;
            return `${km}`;
          }),
          font: label_font,
          stroke: label_color,
          grid: { stroke: grid_color },
          ticks: { stroke: grid_color },
        },
        {
          scale: "m",
          side: 3,
          font: label_font,
          stroke: label_color,
          grid: { stroke: grid_color },
          ticks: { stroke: grid_color },
        },
        {
          scale: "%",
          side: 1,
          font: label_font,
          stroke: label_color,
          grid: { show: false },
          ticks: { stroke: grid_color },
          values: (_u, splits) => splits.map((s) => `${s}%`),
        },
      ],
      series: [
        {},
        {
          label: "Elevation",
          scale: "m",
          stroke: elev_color,
          width: 2.5,
          fill: elev_fill,
          points: { show: false },
        },
        {
          label: "Slope",
          scale: "%",
          stroke: slope_color,
          width: 1,
          points: { show: false },
        },
      ],
      plugins: [this.#cursor_plugin()],
    };
    this.#plot.current = new uPlot(opts, this.#data.current, host);
  }

  #cursor_plugin(): uPlot.Plugin {
    let tip: HTMLDivElement;
    return {
      hooks: {
        init: (u) => {
          tip = document.createElement("div");
          tip.className = "route-profile-tip";
          tip.hidden = true;
          u.over.appendChild(tip);

          u.over.addEventListener("mouseleave", () => {
            tip.hidden = true;
            this.#on_leave.current();
          });
        },
        setCursor: (u) => {
          const i = u.cursor.idx;
          if (i == null) {
            tip.hidden = true;
            this.#on_leave.current();
            return;
          }
          const p = this.#track.current[i];
          if (p === undefined)
            return;
          tip.hidden = false;
          tip.innerHTML =
            `<b>${(p.dist_m / 1000).toFixed(1)} km</b>` +
            `<span>ETA ${fmt_eta(p.dur_s)}</span>` +
            `<span>${Math.round(p.elev_m)} m</span>` +
            `<span>${p.slope.toFixed(1)} %</span>`;

          const left = u.valToPos(p.dist_m / 1000, "x"); /* css px in over */
          const gap = 32;
          const tw = tip.offsetWidth;
          const over_w = u.over.clientWidth;
          let x = left + gap;   /* default: right of the cursor */
          if (x + tw > over_w)  /* would overflow: flip to left */
            x = left - gap - tw;
          if (x < 0)            /* clamp at the left edge */
            x = 0;
          tip.style.transform = `translateX(${x}px)`;
          this.#on_hover.current(p);
        },
      },
    };
  }
}

/* Elevation and slope profile for one route's track. Hovering a sample reports
 * its point so the card can echo the spot on the map.
 */
export function RouteProfile(props: {
  track: TrackPoint[];
  onHover: (point: TrackPoint) => void;
  onLeave: () => void;
}) {
  const profile = new ProfileView(props.onHover, props.onLeave);

  useEffect(() => profile.mount(), []);
  useEffect(() => { profile.set_track(props.track); }, [props.track]);

  return (
    <div
      ref={profile.host}
      className="route-profile"
      style={{ height: PROFILE_H }}
    />
  );
}
