import { uiText, useUiLocale } from "@/shared/i18n";
import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import { ProductHomePage } from "@/pages/product-home";

const StudioApplication = lazy(() => import("@/app/StudioApplication"));

/** Keep the public introduction independent of workspace queries and startup. */
export default function App() {
  useUiLocale();
  return (
    <Routes>
      <Route path="/" element={<ProductHomePage />} />
      <Route path="*" element={<Suspense fallback={<p role="status" className="p-8">{uiText("正在打开知行…")}</p>}><StudioApplication /></Suspense>} />
    </Routes>
  );
}
