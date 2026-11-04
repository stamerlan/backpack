import { useEffect, useState } from "react";
import { Spinner } from "@fluentui/react-components";
import "./splash.css";

export function Splash() {
  const [ready, set_ready] = useState(false);

  useEffect(() => {
    window.set_ready = () => set_ready(true);
    return () => { window.set_ready = () => {}; };
  }, []);

  return (
    <div className={ready ? "splash ready" : "splash"} aria-busy={!ready}>
      <img className="splash-icon" src="icons/app.png" alt="" />
      <Spinner className="splash-spinner" size="small" />
    </div>
  );
}
