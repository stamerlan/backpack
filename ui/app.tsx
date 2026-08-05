import { useState } from "react";
import {
  FluentProvider,
  makeStyles,
  webLightTheme,
} from "@fluentui/react-components";
import { AppBar } from "./app-bar";
import { Assist } from "./assist";
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
  doc: {
    flex: "1 1 auto",
    minHeight: 0,
    display: "flex",
    flexDirection: "row",
    position: "relative",
  },
});

export function App() {
  const styles = use_styles();
  const [menu_open, set_menu_open] = useState(false);
  const [title, set_title] = useState("");
  const [assist_open, set_assist_open] = useState(false);

  return (
    <FluentProvider theme={webLightTheme} className={styles.app}>
      <AppBar
        title={title}
        assist_open={assist_open}
        on_menu_click={() => set_menu_open(true)}
        on_assist_toggle={() => set_assist_open((o) => !o) }
      />
      <NotifyHost />
      <div className={styles.doc}>
        <Doc on_title_change={set_title} />
        <Assist open={assist_open} on_close={() => set_assist_open(false)} />
      </div>
      <Menu open={menu_open} show_menu={set_menu_open} />
      <DialogHost />
      <Busy />
    </FluentProvider>
  );
}
