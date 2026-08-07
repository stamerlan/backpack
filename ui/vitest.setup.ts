import "@testing-library/jest-dom/vitest";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

/* unmount between tests hands the ui-api entries back to their defaults */
afterEach(cleanup);

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
