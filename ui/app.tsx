import { useEffect, useState } from "react";
import {
  FluentProvider,
  webDarkTheme,
  webLightTheme,
} from "@fluentui/react-components";
import { AppBar } from "./app-bar";
import { Assist } from "./assist";
import { Busy } from "./busy";
import { Doc } from "./doc";
import { DialogHost } from "./dialog-host";
import { Menu } from "./menu";
import { NotifyHost } from "./notify";
import { SettingsDialog } from "./settings";
import "./app.css";

type ThemeMode = "system" | "light" | "dark";

export function App() {
  const [menu_open, set_menu_open] = useState(false);
  const [title, set_title] = useState("");
  const [assist_open, set_assist_open] = useState(false);
  const [theme_mode, set_theme_mode] = useState<ThemeMode>("system");
  const [sys_theme_dark, set_sys_theme_dark] = useState(
    () => window.matchMedia("(prefers-color-scheme: dark)").matches
  );

  /* Track the OS preference so "Follow system" reacts without a restart. */
  useEffect(() => {
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const on_change = (e: MediaQueryListEvent) => set_sys_theme_dark(e.matches);
    query.addEventListener("change", on_change);
    return () => query.removeEventListener("change", on_change);
  }, []);

  useEffect(() => {
    window.set_theme_mode = (mode) =>
      set_theme_mode(mode === "system" || mode === "light" || mode === "dark"
        ? mode : "system"
      );
    return () => { window.set_theme_mode = () => {}; };
  }, []);

  const is_dark_theme = (
    theme_mode === "dark" || (theme_mode === "system" && sys_theme_dark)
  );

  return (
    <FluentProvider
      theme={is_dark_theme ? webDarkTheme : webLightTheme}
      className="app"
    >
      <AppBar
        title={title}
        assist_open={assist_open}
        on_menu_click={() => set_menu_open(true)}
        on_assist_toggle={() => set_assist_open((o) => !o) }
      />
      <NotifyHost />
      <div className="app-body">
        <Doc on_title_change={set_title} />
        <Assist open={assist_open} />
      </div>
      <Menu open={menu_open} show_menu={set_menu_open} />
      <DialogHost />
      <SettingsDialog />
      <Busy />
    </FluentProvider>
  );
}