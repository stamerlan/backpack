/* Serialize Python API calls so the backend sees user actions in order.
 * Each call is chained onto action_chain; .then(cb) adopts the api promise
 * cb returns, so the next link cannot fire until Python has responded. This
 * keeps one call in flight at a time, in the order calls were enqueued.
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

function api_call(name: string, ...args: unknown[]): Promise<unknown> {
  const result = action_chain.then(() => {
    const api = window.pywebview?.api;
    if (api === undefined)
      throw new Error("pywebview.api is not available");
    return api.dispatch(name, ...args);
  });
  action_chain = result.catch((e) => console.error(`${name}() failed`, e));
  return result; /* caller sees the real value or error */
}

/* Backend exposed methods */
interface Api {
  new_doc(): Promise<unknown>;
  open_doc(filename?: string): Promise<unknown>;
  save_doc(filename?: string | null, save_as?: boolean): Promise<unknown>;
  open_settings(): Promise<unknown>;
  open_logs(): Promise<unknown>;
  remove_recent(filename: string): Promise<unknown>;
  set_theme(mode: string): Promise<unknown>;
  set_locale(locale: string, units: string): Promise<unknown>;
  set_trip_info(
    card_id: string, title: string, notes: string
  ): Promise<unknown>;
  add_route(): Promise<unknown>;
  set_route_info(
    card_id: string, title: string, notes: string
  ): Promise<unknown>;
  remove_route(card_id: string): Promise<unknown>;
  move_route(card_id: string, after_id: string | null): Promise<unknown>;
  add_chat(): Promise<unknown>;
  del_chat(chat_id: string): Promise<unknown>;
  ask_assist(
    chat_id: string, model_id: string, prompt: string
  ): Promise<unknown>;
  stop_assist(chat_id: string): Promise<unknown>;
}

const api = new Proxy({} as Api, {
  get: (_t, name: string) => (...args: unknown[]) => api_call(name, ...args),
});

export default api;
