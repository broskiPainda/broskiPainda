import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import App from "./App.jsx";
import "./index.css";
import AnalysisView from "./pages/AnalysisView.jsx";
import CaseCache from "./pages/CaseCache.jsx";
import History from "./pages/History.jsx";
import ScenarioInput from "./pages/ScenarioInput.jsx";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<App />}>
          <Route index element={<ScenarioInput />} />
          <Route path="analysis/:scenarioId" element={<AnalysisView />} />
          <Route path="cache" element={<CaseCache />} />
          <Route path="history" element={<History />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/service-worker.js").catch(() => {
      // Non-fatal: the app works fine without offline support.
    });
  });
}
