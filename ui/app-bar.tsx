/* Slim toolbar spanning the window above the work area. It is the home for
 * window-level chrome: the menu button, the open document title and the
 * assistant toggle, so nothing floats over the content any more.
 *
 * Properties:
 *   - title: The open trip's title, empty for one not named yet.
 *   - filename: The open file's base name, or null for a trip not saved to a
 *     file yet. Shown under the title so the source is always visible.
 *   - dirty: Whether the trip has unsaved changes, shown as a dot by the title.
 *   - assist_open: Whether the assistant panel is out, which the toggle
 *     shows as its pressed state.
 *   - on_menu_click: Opens the slide-out menu.
 *   - on_assist_toggle: Shows or hides the assistant panel.
 */
import {
  mergeClasses,
  Toolbar,
  ToolbarButton,
  ToolbarToggleButton,
} from "@fluentui/react-components";
import { useTranslation } from "react-i18next";
import { icon } from "./icon";
import "./app-bar.css";

export function AppBar(props: {
  title: string;
  filename: string | null;
  dirty: boolean;
  assist_open: boolean;
  on_menu_click: () => void;
  on_assist_toggle: () => void;
}) {
  const { t } = useTranslation();
  const has_title = props.title.trim().length > 0;
  const assist_label = props.assist_open
    ? t("app_bar.hide_assistant")
    : t("app_bar.show_assistant");

  return (
    <header className="app-bar">
      <Toolbar
        className="app-bar-toolbar"
        aria-label={t("app_bar.label")}
        checkedValues={{ assist: props.assist_open ? ["on"] : [] }}
        onCheckedValueChange={() => props.on_assist_toggle()}
      >
        <ToolbarButton
          appearance="subtle"
          title={t("app_bar.open_menu")}
          aria-label={t("app_bar.open_menu")}
          icon={icon("menu")}
          onClick={props.on_menu_click}
        />
        <div className="app-bar-heading">
          <span className="app-bar-titleline">
            <span
              className={mergeClasses("app-bar-title", !has_title && "untitled")}
            >
              {has_title ? props.title : t("common.untitled_trip")}
            </span>
            {props.dirty && (
              <span
                className="app-bar-dirty"
                role="img"
                aria-label={t("app_bar.unsaved")}
                title={t("app_bar.unsaved")}
              />
            )}
          </span>
          {props.filename && (
            <span className="app-bar-filename" title={props.filename}>
              {props.filename}
            </span>
          )}
        </div>
        <ToolbarToggleButton
          appearance="subtle"
          name="assist"
          value="on"
          title={assist_label}
          aria-label={assist_label}
          icon={icon("panel")}
        />
      </Toolbar>
    </header>
  );
}
