/* Shared helpers for the localized UI specs. render_ui mounts inside the
 * Fluent and i18next providers so components read the same catalog the app
 * uses, and set_locale drives the very bridge the backend calls, waiting for
 * the async catalog swap so the next assertion sees the new language and
 * units. t is bound to the shared instance so specs assert against catalog
 * keys instead of hardcoded English. act_bridge fires any backend bridge
 * inside act so the state update it triggers never escapes a spec's act(...)
 * scope.
 */
import type { ReactElement } from "react";
import { act, render, type RenderResult } from "@testing-library/react";
import { FluentProvider, webLightTheme } from "@fluentui/react-components";
import { I18nextProvider } from "react-i18next";
import i18n from "./i18n";

export { i18n };

/* Translate a key against the shared instance the components render through. */
export const t = i18n.t.bind(i18n);

/* Mount a subtree with the providers the real app wraps around it. */
export function render_ui(ui: ReactElement): RenderResult {
  return render(
    <FluentProvider theme={webLightTheme}>
      <I18nextProvider i18n={i18n}>{ui}</I18nextProvider>
    </FluentProvider>,
  );
}

/* Push a locale the way the backend does and resolve once the catalog and
 * the unit formatters have settled, so callers can await the swap.
 */
export function set_locale(tag: string, units: string): Promise<void> {
  /* Wrap the swap in act: changeLanguage re-renders subscribed components
   * when it resolves, and without act React warns that the update escaped a
   * test's act(...) scope. */
  return act(
    () =>
      new Promise<void>((resolve) => {
        window.addEventListener("set_locale", () => resolve(), { once: true });
        window.set_locale(tag, units);
      }),
  );
}

/* Return to the English, metric defaults every other spec assumes. */
export function reset_locale(): Promise<void> {
  return set_locale("en", "metric");
}

/* Run a backend bridge call inside act and return its value. Bridges like
 * window.set_busy, window.notify or window.doc push straight into component
 * state, so a bare call updates React outside a test act(...) scope. Under
 * heavy load that update races the next findBy flush and prints a "not
 * wrapped in act" warning; committing it inside act first closes the race.
 *
 * This stays synchronous and hands the raw value back. The bridges that open a
 * banner or dialog return a promise that only settles on a later click, so it
 * must reach the caller unawaited; an async wrapper would make the caller await
 * that pending promise and hang the test. Callers keep the value as-is, exactly
 * as they would a bare bridge call. */
export function act_bridge<T>(fn: () => T): T {
  let result!: T;
  act(() => {
    result = fn();
  });
  return result;
}
