import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import "@xyflow/react/dist/style.css";
import App from "./App";
import "./styles/globals.css";
import { hydrateStudioSettingsDom } from "./stores/studioSettingsStore";
import { applyUiLocale, useUiLocaleStore } from "@/shared/i18n";

hydrateStudioSettingsDom();
applyUiLocale(useUiLocaleStore.getState().locale);

// Keep existing descendant routes and providers; data routing enables complete POP/PUSH guards.
const router = createBrowserRouter([{ path: "*", element: <App /> }]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
