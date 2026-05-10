import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "@xyflow/react/dist/style.css";
import App from "./App";
import "./styles/globals.css";
import { hydrateStudioSettingsDom } from "./stores/studioSettingsStore";

hydrateStudioSettingsDom();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
