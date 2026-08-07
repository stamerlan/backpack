/* Slim toolbar spanning the window above the work area. It is the home for
 * window-level chrome: the menu button, the open document title and the
 * assistant toggle, so nothing floats over the content any more.
 */
import {
  mergeClasses,
  Button,
  ToggleButton,
} from "@fluentui/react-components";
import { icon } from "./icon";
import "./app-bar.css";

export function AppBar(props: {
  title: string;
  assist_open: boolean;
  on_menu_click: () => void;
  on_assist_toggle: () => void;
}) {
  const has_title = props.title.trim().length > 0;

  return (
    <header className="app-bar">
      <Button
        appearance="subtle"
        title="Open menu"
        aria-label="Open menu"
        icon={icon("menu")}
        onClick={props.on_menu_click}
      />
      <span className={mergeClasses("app-bar-title", !has_title && "untitled")}>
        {has_title ? props.title : "Untitled trip"}
      </span>
      <ToggleButton
        appearance="subtle"
        checked={props.assist_open}
        title={props.assist_open ? "Hide assistant" : "Show assistant"}
        aria-label={props.assist_open ? "Hide assistant" : "Show assistant"}
        icon={icon("panel")}
        onClick={props.on_assist_toggle}
      />
    </header>
  );
}
