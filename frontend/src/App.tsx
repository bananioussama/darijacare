// Pages de la plateforme (cahier des charges, Tableau 29). Les pages du personnel sont
// chargées à la demande : le chat client n'embarque ni Recharts ni la console.
import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router";

import Layout from "./components/Layout";
import RequireRole from "./components/RequireRole";
import ChatPage from "./pages/ChatPage";
import CreditsPage from "./pages/CreditsPage";
import HistoryPage from "./pages/HistoryPage";
import LoginPage from "./pages/LoginPage";
import NotFoundPage from "./pages/NotFoundPage";

const AdminPage = lazy(() => import("./pages/AdminPage"));
const ConsolePage = lazy(() => import("./pages/ConsolePage"));
const DashboardPage = lazy(() => import("./pages/DashboardPage"));

export default function App() {
  return (
    <Suspense fallback={<p className="p-6 text-texte-2">Chargement…</p>}>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<ChatPage />} />
          <Route path="historique" element={<HistoryPage />} />
          <Route path="connexion" element={<LoginPage />} />
          <Route
            path="console"
            element={
              <RequireRole roles={["conseiller", "admin"]}>
                <ConsolePage />
              </RequireRole>
            }
          />
          <Route
            path="tableau-de-bord"
            element={
              <RequireRole roles={["conseiller", "ml", "admin"]}>
                <DashboardPage />
              </RequireRole>
            }
          />
          <Route
            path="administration"
            element={
              <RequireRole roles={["ml", "admin"]}>
                <AdminPage />
              </RequireRole>
            }
          />
          <Route path="credits" element={<CreditsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
