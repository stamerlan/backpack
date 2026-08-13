/* One route of the trip: a header with the title, the distance and elevation
 * badges, then the map, the elevation profile and the route notes. Edits are
 * reported upwards on every keystroke and sent to the backend on blur.
 *
 * Properties:
 *   - id: Model id of the route, quoted back on every commit.
 *   - title: Route title, owned by the document view.
 *   - notes: Route notes as markdown, owned by the document view.
 *   - stats: Distance, duration and elevation totals, null while unknown.
 *   - track: The route's own sampled points, drawn by the profile chart.
 *   - overlay: What the map paints: this route over its dimmed siblings.
 *   - route_loading: Shows the header spinner while details load.
 *   - on_change: Reports the edited title and notes on every keystroke.
 *   - on_remove: Drops the card once the backend has been told.
 *   - on_grip_down: Arms the grip so the document may lift this card.
 *   - on_grip_up: Disarms the grip.
 *
 * State:
 *   - folded: Hides the map, profile and notes, leaving only the header.
 *   - hover: Point the profile is hovering, echoed as a dot on the map.
 */
import { useState } from "react";
import {
  Badge,
  Button,
  Card,
  Input,
  Spinner,
} from "@fluentui/react-components";
import { useTranslation } from "react-i18next";
import type { TFunction } from "i18next";
import { dist_str, elev_str } from "./i18n";
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
import "./route-card.css";

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

function elev_title(t: TFunction, stats: RouteStats): string {
  /* The badge only has room for the two totals, so the rest of the elevation
   * numbers ride along in its tooltip. Each value carries its own unit so the
   * whole tooltip follows the active system.
   */
  const net = stats.elev_net_m;
  return t("route_card.elevation_hint", {
    net: (net > 0 ? "+" : "") + elev_str(net),
    vertical: elev_str(stats.vertical_m),
    min: elev_str(stats.elev_min_m),
    max: elev_str(stats.elev_max_m),
    mean: elev_str(stats.elev_mean_m),
  });
}

export function RouteCard(props: {
  id: string;
  title: string;
  notes: string;
  stats: RouteStats | null;
  track: TrackPoint[];
  overlay: MapOverlay;
  route_loading?: boolean;
  on_change: (title: string, notes: string) => void;
  on_remove: (id: string) => void;
  on_grip_down?: () => void;
  on_grip_up?: () => void;
}) {
  const { t } = useTranslation();
  const [folded, set_folded] = useState(false);
  const [hover, set_hover] = useState<Coord | null>(null);
  const stats = props.stats;

  const commit = (): void => {
    void api.set_route_info(props.id, props.title, props.notes);
  };

  /* Deleting a route is destructive, so ask before telling the backend. */
  const remove = async (): Promise<void> => {
    const confirmed = await window.show_dialog(
      t("route_card.delete_confirm_title"),
      t("route_card.delete_confirm_text"),
      [
        { title: t("route_card.delete_confirm_cancel"), result: false },
        {
          title: t("route_card.delete_confirm_ok"),
          result: true,
          appearance: "primary",
        },
      ],
    );
    if (!confirmed)
      return;
    void api.remove_route(props.id);
    props.on_remove(props.id);
  };

  return (
    <Card className="route-card">
      <div className="route-card-header">
        <button
          type="button"
          className="icon-btn route-card-grip"
          title={t("route_card.reorder")}
          aria-label={t("route_card.reorder")}
          onPointerDown={() => props.on_grip_down?.()}
          onPointerUp={() => props.on_grip_up?.()}
        >
          {icon("grip", 12)}
        </button>
        <Button
          appearance="subtle"
          size="small"
          title={folded ? t("route_card.unfold") : t("route_card.fold")}
          aria-label={folded ? t("route_card.unfold") : t("route_card.fold")}
          aria-expanded={!folded}
          icon={
            <span className={"chevron" + (folded ? " folded" : "")}>
              {icon("chevron", 12)}
            </span>
          }
          onClick={() => set_folded((f) => !f)}
        />
        <Input
          className="route-card-title"
          appearance="underline"
          placeholder={t("route_card.untitled")}
          value={props.title}
          onChange={(_event, data) => props.on_change(data.value, props.notes)}
          onKeyDown={(event) => {
            /* Enter commits the same way leaving the field does. */
            if (event.key === "Enter")
              event.currentTarget.blur();
          }}
          onBlur={commit}
        />
        {stats && (
          <div className="route-card-summary">
            <Badge
              appearance="tint"
              color="informative"
              shape="rounded"
              title={t("route_card.distance_hint")}
            >
              {dist_str(stats.dist_m)}
            </Badge>
            <Badge
              appearance="tint"
              color="informative"
              shape="rounded"
              title={t("route_card.duration_hint")}
            >
              {fmt_hm(stats.dur_s)}
            </Badge>
            <Badge
              appearance="tint"
              color="informative"
              shape="rounded"
              title={elev_title(t, stats)}
            >
              {`\u2197${elev_str(stats.ascent_m, false)} ` +
                `\u2198${elev_str(stats.descent_m)}`}
            </Badge>
          </div>
        )}
        {props.route_loading && (
          <Spinner size="tiny"
            title={t("route_card.loading")}
            aria-label={t("route_card.loading")}
          />
        )}
        <Button
          appearance="subtle"
          title={t("route_card.delete")}
          aria-label={t("route_card.delete")}
          icon={icon("trash", 16)}
          onClick={() => void remove()}
        />
      </div>
      {!folded && (
        <div className="route-card-body">
          <RouteMap overlay={props.overlay} hover={hover} />
          {props.track.length > 0 && (
            <RouteProfile
              track={props.track}
              on_hover={set_hover}
              on_leave={() => set_hover(null)}
            />
          )}
          <MdInput
            placeholder={t("route_card.notes_placeholder")}
            value={props.notes}
            min_height={120}
            on_change={(value) => props.on_change(props.title, value)}
            on_commit={commit}
          />
        </div>
      )}
    </Card>
  );
}
