/* Everything the backend may call on the frontend, mirroring UI and Assist
 * in src/backpack/ui.py the way api.ts mirrors api.py. Each entry is seeded
 * here and claimed by its host component for as long as that host is
 * mounted.
 *
 * A call arriving with no host throws when the backend awaits an answer,
 * since a dropped request would leave it waiting forever. The rest are
 * seeded as no-ops: with no host there is simply nothing to show.
 */
import type { AssistApi } from "./assist";
import type { DialogAction } from "./dialog-host";
import type { DocApi } from "./doc";
import type { RecentItem } from "./menu";
import type { NotifyAction, NotifyIntent } from "./notify";
import type { SettingsValues } from "./settings";

declare global {
  interface Window {
    doc: DocApi | null;
    assist: AssistApi | null;
    menu: { set_recent(items: RecentItem[]): void } | null;

    show_dialog(
      title: string, text: string, actions?: Iterable<DialogAction>,
    ): Promise<unknown>;
    show_settings_dialog(
      settings: Record<string, unknown>,
    ): Promise<SettingsValues | null>;
    notify(
      message: string,
      intent?: NotifyIntent,
      title?: string,
      actions?: Iterable<NotifyAction>,
    ): Promise<unknown>;
    clear_notify(): void;
    set_busy(busy: boolean, label?: string): void;
    set_theme_mode(mode: string): void;
    set_locale(tag: string, units: string): void;
    set_doc_state(filename: string | null, dirty: boolean): void;
  }
}

/* Stands in for an entry point whose host is not mounted. */
export function not_mounted(what: string): () => never {
  return () => { throw new Error(`${what} is not mounted`); };
}

window.doc = null;
window.assist = null;
window.menu = null;
window.show_dialog = not_mounted("dialog host");
window.show_settings_dialog = not_mounted("settings dialog");
window.notify = not_mounted("notify host");
window.clear_notify = () => {};
window.set_busy = () => {};
window.set_theme_mode = () => {};
window.set_locale = () => {};
window.set_doc_state = () => {};
