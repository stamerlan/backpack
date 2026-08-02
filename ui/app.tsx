import { useState } from "react";
import {
  FluentProvider,
  makeStyles,
  Text,
  webLightTheme,
} from "@fluentui/react-components";
import { AppBar } from "./app-bar";
import { DialogHost } from "./dialog-host";
import { Menu } from "./menu";

/* The app bar sits above the work area, so the root stacks the two and pins
 * the pair to the viewport height. The content takes whatever is left and
 * scrolls on its own.
 */
const use_styles = makeStyles({
  app: {
    height: "100%",
    display: "flex",
    flexDirection: "column",
  },
  content: {
    flex: "1 1 auto",
    minHeight: 0,
    overflowY: "auto",
    padding: "12px",
  },
});

export function App() {
  const styles = use_styles();
  const [menu_open, set_menu_open] = useState(false);

  return (
    <FluentProvider theme={webLightTheme} className={styles.app}>
      <AppBar on_menu_click={() => set_menu_open(true)} />
      <main className={styles.content}>
        <Text size={600} weight="bold" block>Hello, world</Text>
      </main>
      <Menu open={menu_open} show_menu={set_menu_open} />
      <DialogHost />
    </FluentProvider>
  );
}
