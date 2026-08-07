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

export function Busy() {
  const styles = use_styles();
  const [state, set_state] = useState<BusyState>({ busy: false, label: "" });

  useEffect(() => {
    window.set_busy = (busy, label = "") => set_state({ busy, label });
    return () => { window.set_busy = () => {}; };
  }, []);

  if (!state.busy)
    return null;

  return (
    <div className={styles.overlay} aria-busy="true">
      <Spinner label={state.label || undefined} />
    </div>
  );
}