/* Send backend calls through window.pywebview.api, serialized on action_chain
 * so one is in flight at a time and Python sees them in order. Dispatch is
 * fire-and-forget: no result comes back, so every method returns void. Both
 * hosts publish the bridge under that name - pywebview on macOS, a native shim
 * over the WebView2 web-message channel on Windows.
 */
let action_chain: Promise<unknown> = Promise.resolve();

interface PyWebView {
  api: { dispatch(name: string, ...args: unknown[]): Promise<unknown> };
}

declare global {
  interface Window {
    pywebview?: PyWebView;
  }
}

function api_call(name: string, ...args: unknown[]): void {
  action_chain = action_chain
    .then(() => {
      const api = window.pywebview?.api;
      if (api === undefined)
        throw new Error("pywebview.api is not available");
      return api.dispatch(name, ...args);
    })
    .catch((e) => console.error(`${name}() failed`, e));
}

/* Backend exposed methods */
interface Api {
  new_doc(): void;
  open_doc(filename?: string): void;
  save_doc(filename?: string | null, save_as?: boolean): void;
  open_settings(): void;
  open_logs(): void;
  remove_recent(filename: string): void;
  set_theme(mode: string): void;
  set_locale(locale: string, units: string): void;
  set_trip_info(card_id: string, title: string, notes: string): void;
  add_route(): void;
  set_route_info(card_id: string, title: string, notes: string): void;
  remove_route(card_id: string): void;
  move_route(card_id: string, after_id: string | null): void;
  add_chat(): void;
  del_chat(chat_id: string): void;
  ask_assist(chat_id: string, model_id: string, prompt: string): void;
  stop_assist(chat_id: string): void;
}

const api = new Proxy({} as Api, {
  get: (_t, name: string) => (...args: unknown[]) => api_call(name, ...args),
});

export default api;
