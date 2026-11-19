import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import App from "../App";
import { AuthProvider } from "../lib/auth";
import { writeJson } from "../lib/storage";
import { json, mockFetch } from "../test/fetchMock";

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}

const PASSWORD = "un-mot-de-passe-solide-42";

describe("Inscription du personnel", () => {
  it("offers « S'inscrire » to visitors and sends a request that waits for an admin", async () => {
    const calls = mockFetch({
      "POST /auth/register": () =>
        json(
          {
            detail:
              "Demande enregistrée : un administrateur doit valider le compte avant la première connexion.",
          },
          202,
        ),
    });
    const user = userEvent.setup();
    renderAt("/connexion");
    // Bouton dans le menu et sur la page de connexion.
    expect(screen.getAllByRole("link", { name: "S'inscrire" })).toHaveLength(2);
    await user.click(within(screen.getByRole("main")).getByRole("link", { name: "S'inscrire" }));
    expect(
      await screen.findByRole("heading", { name: "Inscription du personnel" }),
    ).toBeInTheDocument();

    await user.type(screen.getByLabelText("Identifiant"), "nouveau.conseiller");
    await user.type(screen.getByLabelText("Mot de passe (12 caractères min.)"), PASSWORD);
    await user.type(screen.getByLabelText("Confirmer le mot de passe"), "un-autre-mot-de-passe");
    await user.click(screen.getByRole("button", { name: "Envoyer la demande" }));
    expect(screen.getByRole("alert")).toHaveTextContent("ne correspondent pas");
    expect(calls).toHaveLength(0);

    await user.clear(screen.getByLabelText("Confirmer le mot de passe"));
    await user.type(screen.getByLabelText("Confirmer le mot de passe"), PASSWORD);
    await user.selectOptions(screen.getByLabelText("Rôle demandé"), "ml");
    await user.click(screen.getByRole("button", { name: "Envoyer la demande" }));
    expect(await screen.findByRole("heading", { name: "Demande envoyée" })).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("un administrateur doit valider");
    expect(calls[0]).toMatchObject({
      method: "POST",
      path: "/auth/register",
      body: { username: "nouveau.conseiller", password: PASSWORD, requested_role: "ml" },
    });
  });

  it("shows the API's reason when the request is refused", async () => {
    mockFetch({ "POST /auth/register": () => json({ detail: "Identifiant déjà utilisé." }, 409) });
    const user = userEvent.setup();
    renderAt("/inscription");
    await user.type(screen.getByLabelText("Identifiant"), "admin");
    await user.type(screen.getByLabelText("Mot de passe (12 caractères min.)"), PASSWORD);
    await user.type(screen.getByLabelText("Confirmer le mot de passe"), PASSWORD);
    await user.click(screen.getByRole("button", { name: "Envoyer la demande" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Identifiant déjà utilisé.");
  });

  it("lets the administrator validate or refuse pending requests", async () => {
    writeJson("session", "darijacare.staff", {
      username: "admin1",
      role: "admin",
      token: "jeton-admin",
      expiresAt: Date.now() + 15 * 60 * 1000,
    });
    const pending = (id: string, username: string, role: "conseiller" | "ml") => ({
      id,
      username,
      role,
      active: true,
      pending: true,
      created_at: "2026-11-19T10:00:00Z",
    });
    const calls = mockFetch({
      "GET /kb/fiches": () => json([]),
      "GET /models": () => json([]),
      "GET /admin/users": () =>
        json([
          pending("u1", "nouveau.conseiller", "conseiller"),
          pending("u2", "inconnu", "ml"),
          {
            id: "u3",
            username: "admin1",
            role: "admin",
            active: true,
            pending: false,
            created_at: "2026-11-18T10:00:00Z",
          },
        ]),
      "PATCH /admin/users/u1": (call) =>
        json({
          ...pending("u1", "nouveau.conseiller", "conseiller"),
          role: (call.body as { role: string }).role,
          pending: false,
        }),
      "DELETE /admin/users/u2": () => json(null, 204),
    });
    const user = userEvent.setup();
    renderAt("/administration");
    expect(
      await screen.findByRole("heading", { name: "Demandes d'inscription en attente (2)" }),
    ).toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("Rôle accordé", { selector: "#role-u1" }), "ml");
    await user.click(
      screen.getByRole("button", { name: "Valider l'inscription de nouveau.conseiller" }),
    );
    expect(
      await screen.findByText(/Compte nouveau\.conseiller validé \(ML \/ data\)/),
    ).toBeVisible();
    expect(calls.find((c) => c.method === "PATCH")?.body).toEqual({
      action: "valider",
      role: "ml",
    });

    await user.click(screen.getByRole("button", { name: "Refuser l'inscription de inconnu" }));
    expect(await screen.findByText("Demande de inconnu refusée et supprimée.")).toBeVisible();
    expect(
      screen.getByRole("heading", { name: "Demandes d'inscription en attente (0)" }),
    ).toBeInTheDocument();
    expect(calls.find((c) => c.method === "DELETE")?.headers.authorization).toBe(
      "Bearer jeton-admin",
    );
  });
});
