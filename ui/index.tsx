/* Entry point. Seeds the surface the backend calls and the styles shared
 * across components, both before anything can reach them, then mounts the
 * app under the root element index.html provides.
 */
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./ui-api";
import "./styles.css";
import { App } from "./app";

const root = document.getElementById("root");
if (root === null)
  throw new Error("#root is missing from index.html");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>
);
