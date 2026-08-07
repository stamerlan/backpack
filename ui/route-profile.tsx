/* Elevation and slope profile for one route's track, drawn with uPlot. uPlot
 * owns everything inside the host element, so the chart is built once the
 * host has been laid out and driven imperatively after that. Hovering a
 * sample reports it so the card can echo the spot on its map.
 *
 * Properties:
 *   - track: The route's sampled points, from the start of the route.
 *   - on_hover: Reports the sample under the cursor.
 *   - on_leave: Reports that the cursor has left the chart.
 *
 * State:
 *   - profile: The chart, the data behind it and the callbacks its uPlot
 *     plugin reaches for. A ref, because React renders none of it and must
 *     not re-render when it changes.
 */
import { useEffect, useRef } from "react";
import uPlot from "uplot";
import "uplot/dist/uPlot.min.css";
import "./route-profile.css";
import type { TrackPoint } from "./route-map";

/* Fixed chart height, matching the map's minimum, in px. */
const PROFILE_H = 160;

interface Profile {
  plot: uPlot | null;
  track: TrackPoint[];
  data: uPlot.AlignedData | null;
  width: number;
  height: number;
  on_hover: (point: TrackPoint) => void;
  on_leave: () => void;
}

function fmt_eta(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return h ? `${h}h ${m}m` : `${m}m`;
}

/* Follows the cursor: moves the readout box and reports the sample under it.
 * The box flips to the other side of the cursor rather than overflow.
 */
function cursor_plugin(profile: Profile): uPlot.Plugin {
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
          profile.on_leave();
        });
      },
      setCursor: (u) => {
        const i = u.cursor.idx;
        if (i == null) {
          tip.hidden = true;
          profile.on_leave();
          return;
        }
        const p = profile.track[i];
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
        profile.on_hover(p);
      },
    },
  };
}

function options(
  host: HTMLDivElement, profile: Profile, width: number, height: number,
): uPlot.Options {
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

  return {
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
    plugins: [cursor_plugin(profile)],
  };
}

/* The only place that sizes the plot: builds once, resizes after. */
function sync(host: HTMLDivElement, profile: Profile): void {
  if (profile.data === null)
    return;

  const w = Math.floor(host.clientWidth);
  const h = Math.floor(host.clientHeight);
  if (!w || !h) /* not laid out yet: a later observer tick retries */
    return;

  if (profile.plot === null) {
    profile.width = w;
    profile.height = h;
    profile.plot = new uPlot(options(host, profile, w, h), profile.data, host);
    return;
  }
  if (w !== profile.width || h !== profile.height) {
    profile.width = w;
    profile.height = h;
    profile.plot.setSize({ width: w, height: h });
  }
}

export function RouteProfile(props: {
  track: TrackPoint[];
  on_hover: (point: TrackPoint) => void;
  on_leave: () => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const held = useRef<Profile | null>(null);
  const profile = held.current ??= {
    plot: null,
    track: [],
    data: null,
    width: 0,
    height: 0,
    on_hover: props.on_hover,
    on_leave: props.on_leave,
  };

  /* The plugin runs long after this render, so keep it pointed at the
   * callbacks the card is handing over now.
   */
  profile.on_hover = props.on_hover;
  profile.on_leave = props.on_leave;

  useEffect(() => {
    const el = host.current;
    if (el === null)
      return;
    const observer = new ResizeObserver(() => sync(el, profile));
    observer.observe(el);
    return () => {
      observer.disconnect();
      profile.plot?.destroy();
      profile.plot = null;
    };
  }, []);

  useEffect(() => {
    const el = host.current;
    if (el === null)
      return;
    profile.track = props.track;
    profile.data = [
      props.track.map((p) => p.dist_m / 1000),   /* x: km        */
      props.track.map((p) => p.elev_m),          /* elevation, m */
      props.track.map((p) => p.slope),           /* slope, %     */
    ];
    if (profile.plot)
      profile.plot.setData(profile.data);
    else
      requestAnimationFrame(() => sync(el, profile)); /* let layout settle */
  }, [props.track]);

  return (
    <div ref={host} className="route-profile" style={{ height: PROFILE_H }} />
  );
}
