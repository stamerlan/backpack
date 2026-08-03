import { useEffect, useState } from "react";
import { makeStyles, tokens, Spinner } from "@fluentui/react-components";

const use_styles = makeStyles({
  overlay: {
    position: "fixed",
    inset: 0,
    zIndex: 1000,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: tokens.colorBackgroundOverlay,
  },
});

interface BusyState {
  busy: boolean;
  label: string;
}

let apply_busy: ((state: BusyState) => void) | null = null;

export function Busy() {
  const styles = use_styles();
  const [state, set_state] = useState<BusyState>({ busy: false, label: "" });

  useEffect(() => {
    apply_busy = set_state;
    return () => { apply_busy = null; };
  }, []);

  if (!state.busy)
    return null;

  return (
    <div className={styles.overlay} aria-busy="true">
      <Spinner label={state.label || undefined} />
    </div>
  );
}

function set_busy(busy: boolean, label = ""): void {
  apply_busy?.({ busy, label });
}

declare global {
  interface Window {
    set_busy: typeof set_busy;
  }
}

window.set_busy = set_busy;
