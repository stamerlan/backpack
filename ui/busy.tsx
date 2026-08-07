/* The overlay covering the window while the backend works, raised and
 * dropped through window.set_busy. It swallows every click, so a long
 * operation cannot be started twice or interrupted halfway.
 *
 * Properties:
 *   - (none): The backend drives the overlay through the bridge.
 *
 * State:
 *   - state: Whether the overlay is up, and the label under its spinner.
 */
import { useEffect, useState } from "react";
import { Spinner } from "@fluentui/react-components";
import "./busy.css";

interface BusyState {
  busy: boolean;
  label: string;
}

export function Busy() {
  const [state, set_state] = useState<BusyState>({ busy: false, label: "" });

  useEffect(() => {
    window.set_busy = (busy, label = "") => set_state({ busy, label });
    return () => { window.set_busy = () => {}; };
  }, []);

  if (!state.busy)
    return null;

  return (
    <div className="busy-overlay" aria-busy="true">
      <Spinner label={state.label || undefined} />
    </div>
  );
}