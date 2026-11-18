import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import App from "./App";
import { AuthProvider } from "./lib/auth";
import { writeJson } from "./lib/storage";
import { json, mockFetch } from "./test/fetchMock";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}

function signIn(role: "conseiller" | "ml" | "admin"): void {
  writeJson("session", "darijacare.staff", {
    username: `${role}1`,
    role,
    token: `jeton-${role}`,
    expiresAt: Date.now() + 15 * 60 * 1000,
  });
}

describe("App", () => {
  it("sends anonymous visitors of staff pages to the login page", async () => {
    renderAt("/console");
    expect(
      await screen.findByRole("heading", { name: "Connexion du personnel" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Console conseiller" })).toBeNull();
  });

  it("logs in and lands on the role's home page", async () => {
    const calls = mockFetch({
      "POST /auth/login": () =>
        json({ access_token: "jeton-ml", token_type: "bearer", expires_in: 900, role: "ml" }),
      "GET /analytics/summary": () =>
        json({
          periode_jours: 30,
          messages: 12,
          escalades: 3,
          taux_escalade: 0.25,
          latence_ms: { p50: 1700, p95: 1900 },
          par_script: { arabic: 5, arabizi: 4, mixed: 3 },
          par_decision: { reponse_ancree: 9, escalade: 3 },
          top_intentions: [{ intent: "balance_check", messages: 4 }],
          feedback: { utile: 2 },
          modele: {
            version: "v5@8e694ecf",
            evaluation: { dataset: "test", f1_macro: 0.8948, ece: 0.0448 },
          },
        }),
      "GET /analytics/escalades": () =>
        json({ par_statut: { nouveau: 2, en_cours: 1 }, ouvertes_par_niveau: { critique: 1 } }),
    });
    const user = userEvent.setup();
    renderAt("/connexion");
    await user.type(screen.getByLabelText("Identifiant"), "ml1");
    await user.type(screen.getByLabelText("Mot de passe"), "un-mot-de-passe-long");
    await user.click(screen.getByRole("button", { name: "Se connecter" }));
    expect(await screen.findByRole("heading", { name: "Tableau de bord" })).toBeInTheDocument();
    expect(await screen.findByText("0,895")).toBeInTheDocument(); // F1 macro (test)
    expect(screen.getByText("25 %")).toBeInTheDocument();
    expect(screen.getByText("1 900 ms")).toBeInTheDocument();
    expect(calls.find((c) => c.path.startsWith("/analytics/summary"))?.headers.authorization).toBe(
      "Bearer jeton-ml",
    );
    expect(screen.getByRole("link", { name: "Base et modèles" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Console conseiller" })).toBeNull();
  });

  it("tells a role that a page is not for it", async () => {
    signIn("ml");
    renderAt("/console");
    expect(await screen.findByRole("heading", { name: "Accès réservé" })).toBeInTheDocument();
  });

  it("logs out when the API answers 401", async () => {
    signIn("conseiller");
    mockFetch({
      "GET /escalades": () => json({ detail: "Jeton invalide ou expiré." }, 401),
      "GET /intents": () => json([]),
    });
    renderAt("/console");
    expect(
      await screen.findByRole("heading", { name: "Connexion du personnel" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Session expirée");
  });

  it("shows the credits with the CC BY 4.0 attribution", () => {
    renderAt("/credits");
    // Auteur cité pour le jeu de données et pour les modèles.
    expect(screen.getAllByText(/Mohamed\s+Ballouch/)).toHaveLength(2);
    expect(
      screen.getByRole("link", { name: /Creative Commons Attribution 4\.0 International/ }),
    ).toBeInTheDocument();
  });
});
