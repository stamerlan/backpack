import {
  makeStyles,
  mergeClasses,
  tokens,
  Button,
  ToggleButton,
} from "@fluentui/react-components";
import { icon } from "./icon";

/* Slim toolbar spanning the window above the work area. It is the home for
 * window-level chrome: the menu button, the open document title and the
 * assistant toggle, so nothing floats over the content any more.
 */
const use_styles = makeStyles({
  bar: {
    flex: "none",
    display: "flex",
    alignItems: "center",
    gap: "8px",
    height: "40px",
    padding: "0 8px",
    backgroundColor: tokens.colorNeutralBackground1,
    borderBottom: `1px solid ${tokens.colorNeutralStroke2}`,
  },
  title: {
    flex: "1 1 auto",
    minWidth: 0,
    textAlign: "center",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    fontWeight: tokens.fontWeightSemibold,
    color: tokens.colorNeutralForeground2,
  },
  untitled: {
    fontWeight: tokens.fontWeightRegular,
    color: tokens.colorNeutralForeground3,
  },
});

export function AppBar() {
  const styles = use_styles();

  return (
    <header className={styles.bar}>
      <Button
        appearance="subtle"
        title="Open menu"
        aria-label="Open menu"
        icon={icon("menu")}
      />
      <span className={mergeClasses(styles.title, styles.untitled)}>
        Untitled trip
      </span>
      <ToggleButton
        appearance="subtle"
        checked={false}
        title="Show assistant"
        aria-label="Show assistant"
        icon={icon("panel")}
      />
    </header>
  );
}
