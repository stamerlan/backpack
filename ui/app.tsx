import { useState } from "react";
import {
  FluentProvider,
  makeStyles,
  webLightTheme,
} from "@fluentui/react-components";
import { AppBar } from "./app-bar";
import { Busy } from "./busy";
import { Doc } from "./doc";
import { DialogHost } from "./dialog-host";
import { Menu } from "./menu";
import { NotifyHost } from "./notify";

const use_styles = makeStyles({
  app: {
    height: "100%",
    display: "flex",
    flexDirection: "column",
  },
});

export function App() {
  const styles = use_styles();
  const [menu_open, set_menu_open] = useState(false);
  const [title, set_title] = useState("");

  return (
    <FluentProvider theme={webLightTheme} className={styles.app}>
      <AppBar title={title} on_menu_click={() => set_menu_open(true)} />
      <NotifyHost />
      <Doc on_title_change={set_title} />
      <Menu open={menu_open} show_menu={set_menu_open} />
      <DialogHost />
      <Busy />
    </FluentProvider>
  );
}
