import "@testing-library/jest-dom/vitest";
import "./i18n";

/* No afterEach(cleanup) here on purpose. React Testing Library registers its
 * own cleanup afterEach the first time a spec imports it, and test.globals
 * makes that fire. Keeping this shared setup file free of suite-scoped hooks
 * means a mid-run Vite module-runner reload cannot re-run a hook before the
 * runner exists, which is what made every suite fail to find its runner. It
 * also must not import @testing-library/react, or that auto-cleanup would
 * register here, during setup, and bring the hazard back.
 */

/* Fluent UI queries these APIs; jsdom does not implement them. */
if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent() {
      return false;
    },
  })) as unknown as typeof window.matchMedia;
}

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

globalThis.ResizeObserver ??=
  ResizeObserverMock as unknown as typeof ResizeObserver;

window.pywebview ??= {
  api: new Proxy(
    {},
    { get: () => (..._args: unknown[]) => Promise.resolve() },
  ),
} as Window["pywebview"];
