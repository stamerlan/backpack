/* The window shell: the app bar over the notification strip, the document
 * with the assistant beside it, and the menu, dialogs and busy overlay that
 * lie on top. It owns the theme and the locale every one of them is drawn in.
 *
 * Properties:
 *   - (none): index.tsx mounts it.
 *
 * State:
 *   - menu_open: Whether the slide-out menu is showing.
 *   - title: Trip title for the app bar, as the document reports it.
 *   - filename: Base name of the open file, or null for a trip not saved to
 *     a file yet. The backend pushes it through the bridge.
 *   - dirty: Whether the document has unsaved changes, pushed by the backend.
 *   - assist_open: Whether the assistant panel is slid out.
 *   - theme_mode: The theme the user picked, which the backend sets through
 *     the bridge: system, light or dark.
 *   - sys_theme_dark: Whether the OS asks for a dark theme, tracked so
 *     "system" follows it without a restart.
 *   - locale: The last set_locale push (tag and resolved units). Holding it
 *     forces a tree re-render after i18n swaps elev_str and dist_str, so every
 *     number is redrawn in the new system.
 */
import { useEffect, useState } from "react";
import {
  FluentProvider,
  webDarkTheme,
  webLightTheme,
} from "@fluentui/react-components";
import api from "./api";
import { AppBar } from "./app-bar";
import { Assist } from "./assist";
import { Busy } from "./busy";
import { Doc } from "./doc";
import { DialogHost } from "./dialog-host";
import { Menu } from "./menu";
import { NotifyHost } from "./notify";
import { SettingsDialog } from "./settings";
import type { LocaleDetail } from "./i18n";
import "./app.css";

type ThemeMode = "system" | "light" | "dark";

interface Locale {
  tag: string;
  units: string;
}

export function App() {
  const [menu_open, set_menu_open] = useState(false);
  const [title, set_title] = useState("");
  const [filename, set_filename] = useState<string | null>(null);
  const [dirty, set_dirty] = useState(false);
  const [assist_open, set_assist_open] = useState(false);
  const [theme_mode, set_theme_mode] = useState<ThemeMode>("system");
  const [sys_theme_dark, set_sys_theme_dark] = useState(
    () => window.matchMedia("(prefers-color-scheme: dark)").matches
  );
  const [locale, set_locale] = useState<Locale>({
    tag: "en",
    units: "metric",
  });

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

  useEffect(() => {
    window.set_doc_state = (name, is_dirty) => {
      set_filename(name);
      set_dirty(is_dirty);
    };
    return () => { window.set_doc_state = () => {}; };
  }, []);

  useEffect(() => {
    const on_keydown = (e: KeyboardEvent): void => {
      if (e.altKey || !(e.ctrlKey || e.metaKey)) return;
      const key = e.key.toLowerCase();
      /* Notes and titles commit on blur, so flush the focused field
       * first; api.ts serializes calls, so the action waits for that
       * commit.
       */
      const flush = (): void =>
        (document.activeElement as HTMLElement | null)?.blur();
      if (key === "n" && !e.shiftKey) {
        e.preventDefault();
        flush();
        api.new_doc();
      } else if (key === "o" && !e.shiftKey) {
        e.preventDefault();
        flush();
        api.open_doc();
      } else if (key === "s") {
        e.preventDefault();
        flush();
        if (e.shiftKey) api.save_doc(null, true);
        else api.save_doc();
      }
    };
    window.addEventListener("keydown", on_keydown);
    return () => window.removeEventListener("keydown", on_keydown);
  }, []);

  useEffect(() => {
    const on_locale = (event: CustomEvent<LocaleDetail>): void => {
      const { tag, units } = event.detail;
      set_locale({ tag, units });
    };
    window.addEventListener("set_locale", on_locale);
    return () => window.removeEventListener("set_locale", on_locale);
  }, []);

  const is_dark_theme = (
    theme_mode === "dark" || (theme_mode === "system" && sys_theme_dark)
  );

  return (
    <FluentProvider
      theme={is_dark_theme ? webDarkTheme : webLightTheme}
      className="app"
      data-locale={locale.tag}
      data-units={locale.units}
    >
      <AppBar
        title={title}
        filename={filename}
        dirty={dirty}
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
