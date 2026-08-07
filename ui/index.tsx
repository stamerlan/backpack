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
