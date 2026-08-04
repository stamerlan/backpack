import {
  useEffect,
  useState,
  type Dispatch,
  type SetStateAction,
} from "react";
import {
  Badge,
  Button,
  Card,
  Input,
  makeStyles,
  mergeClasses,
  tokens,
} from "@fluentui/react-components";
import api from "./api";
import { icon } from "./icon";
import { MdInput } from "./md-input";
import {
  RouteMap,
  type Coord,
  type MapOverlay,
  type TrackPoint,
} from "./route-map";
import { RouteProfile } from "./route-profile";

export interface RouteStats {
  dist_m: number;
  dur_s: number;
  ascent_m: number;
  descent_m: number;
  vertical_m: number;
  elev_min_m: number;
  elev_max_m: number;
  elev_net_m: number;
  elev_mean_m: number;
}

function fmt_hm(seconds: number): string {
  const total = Math.round(seconds / 60);
  const h = Math.floor(total / 60);
  const m = total % 60;
  return `${h}:${String(m).padStart(2, "0")}`;
}

function fmt_signed(meters: number): string {
  const v = Math.round(meters);
  return v > 0 ? `+${v}` : String(v);
}

function elev_title(stats: RouteStats): string {
  /* The badge only has room for the two totals, so the rest of the
   * elevation numbers ride along in its tooltip. */
  return (
    `Net ${fmt_signed(stats.elev_net_m)} m over ` +
    `${Math.round(stats.vertical_m)} m of vertical\n` +
    `Lowest ${Math.round(stats.elev_min_m)} m, ` +
    `highest ${Math.round(stats.elev_max_m)} m, ` +
    `average ${Math.round(stats.elev_mean_m)} m`
  );
}

const use_styles = makeStyles({
  card: {
    display: "flex",
    flexDirection: "column",
    gap: "8px",
    padding: "8px 12px 12px",
  },
  body: {
    display: "flex",
    flexDirection: "column",
    gap: "8px",
    minWidth: 0,
  },
  header: {
    display: "flex",
    alignItems: "center",
    gap: "8px",
  },
  grip: {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    flex: "none",
    width: "22px",
    height: "28px",
    padding: 0,
    border: "none",
    background: "transparent",
    color: tokens.colorNeutralForeground4,
    cursor: "grab",
    borderRadius: tokens.borderRadiusSmall,
    touchAction: "none",
    ":hover": {
      color: tokens.colorNeutralForeground2,
      background: tokens.colorNeutralBackground3,
    },
    ":active": {
      cursor: "grabbing",
    },
  },
  chevron: {
    display: "inline-flex",
    transition: "transform 0.15s ease",
  },
  chevron_folded: {
    transform: "rotate(-90deg)",
  },
  title: {
    flex: "1 1 auto",
    minWidth: 0,
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
    fontSize: "17px",
    lineHeight: "1.3",
    fontWeight: tokens.fontWeightSemibold,
  },
  summary: {
    display: "flex",
    alignItems: "center",
    gap: "6px",
    flex: "none",
  },
});

class RouteView {
  #id: string;
  #title: string;
  #set_title: Dispatch<SetStateAction<string>>;
  #notes: string;
  #set_notes: Dispatch<SetStateAction<string>>;
  #folded: boolean;
  #set_folded: Dispatch<SetStateAction<boolean>>;
  #hover: Coord | null;
  #set_hover: Dispatch<SetStateAction<Coord | null>>;
  #on_remove: (id: string) => void;

  constructor(
    id: string,
    title: string,
    notes: string,
    on_remove: (id: string) => void,
  ) {
    this.#id = id;
    [this.#title, this.#set_title] = useState(title);
    [this.#notes, this.#set_notes] = useState(notes);
    [this.#folded, this.#set_folded] = useState(false);
    [this.#hover, this.#set_hover] = useState<Coord | null>(null);
    this.#on_remove = on_remove;
  }

  get title(): string {
    return this.#title;
  }

  set title(title: string) {
    this.#set_title(title);
  }

  get notes(): string {
    return this.#notes;
  }

  set notes(notes: string) {
    this.#set_notes(notes);
  }

  get folded(): boolean {
    return this.#folded;
  }

  toggle_fold(): void {
    this.#set_folded((folded) => !folded);
  }

  get hover(): Coord | null {
    return this.#hover;
  }

  set hover(point: Coord | null) {
    this.#set_hover(point);
  }

  commit(): void {
    void api.set_route_info(this.#id, this.#title, this.#notes);
  }

  remove(): void {
    void api.remove_route(this.#id);
    this.#on_remove(this.#id);
  }
}

export function RouteCard(props: {
  id: string;
  title: string;
  notes: string;
  stats: RouteStats | null;
  track: TrackPoint[];
  overlay: MapOverlay;
  on_remove: (id: string) => void;
  on_grip_down?: () => void;
  on_grip_up?: () => void;
}) {
  const styles = use_styles();
  const route = new RouteView(
    props.id, props.title, props.notes, props.on_remove
  );
  const stats = props.stats;

  useEffect(() => {
    route.title = props.title;
    route.notes = props.notes;
  }, [props.title, props.notes]);

  return (
    <Card className={styles.card}>
      <div className={styles.header}>
        <button
          type="button"
          className={styles.grip}
          title="Drag to reorder"
          aria-label="Drag to reorder"
          onPointerDown={() => props.on_grip_down?.()}
          onPointerUp={() => props.on_grip_up?.()}
        >
          {icon("grip", 12)}
        </button>
        <Button
          appearance="subtle"
          size="small"
          title={route.folded ? "Unfold route" : "Fold route"}
          aria-label={route.folded ? "Unfold route" : "Fold route"}
          aria-expanded={!route.folded}
          icon={
            <span
              className={mergeClasses(
                styles.chevron, route.folded && styles.chevron_folded
              )}
            >
              {icon("chevron", 12)}
            </span>
          }
          onClick={() => route.toggle_fold()}
        />
        <Input
          className={styles.title}
          appearance="underline"
          placeholder="Untitled route"
          value={route.title}
          input={{ className: styles.title_input }}
          onChange={(_event, data) => { route.title = data.value; }}
          onKeyDown={(event) => {
            /* Enter commits the same way leaving the field does. */
            if (event.key === "Enter")
              event.currentTarget.blur();
          }}
          onBlur={() => route.commit()}
        />
        {stats && (
          <div className={styles.summary}>
            <Badge
              appearance="tint"
              color="informative"
              shape="rounded"
              title="Route length, elevation included"
            >
              {(stats.dist_m / 1000).toFixed(2)} km
            </Badge>
            <Badge
              appearance="tint"
              color="informative"
              shape="rounded"
              title={
                "Estimated walking time from Tobler's hiking " +
                "function, with a 33% allowance for pack, rests " +
                "and terrain"
              }
            >
              {fmt_hm(stats.dur_s)}
            </Badge>
            <Badge
              appearance="tint"
              color="informative"
              shape="rounded"
              title={elev_title(stats)}
            >
              {`\u2197${Math.round(stats.ascent_m)} ` +
                `\u2198${Math.round(stats.descent_m)} m`}
            </Badge>
          </div>
        )}
        <Button
          appearance="subtle"
          title="Delete route"
          aria-label="Delete route"
          icon={icon("trash", 16)}
          onClick={() => route.remove()}
        />
      </div>
      {!route.folded && (
        <div className={styles.body}>
          <RouteMap overlay={props.overlay} hover={route.hover} />
          {props.track.length > 0 && (
            <RouteProfile
              track={props.track}
              onHover={(point) => { route.hover = point; }}
              onLeave={() => { route.hover = null; }}
            />
          )}
          <MdInput
            placeholder="Notes for this route..."
            value={route.notes}
            min_height={120}
            on_change={(value) => { route.notes = value; }}
            on_commit={() => route.commit()}
          />
        </div>
      )}
    </Card>
  );
}
