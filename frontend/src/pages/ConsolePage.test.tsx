import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";

import type { EscalationDetail, EscalationOut } from "../api/types";
import { resetIntentsCache } from "../components/IntentSelect";
import { AuthProvider } from "../lib/auth";
import { writeJson } from "../lib/storage";
import { json, mockFetch } from "../test/fetchMock";
import ConsolePage from "./ConsolePage";

const ITEM: EscalationOut = {
  id: "e-1",
  case_number: "DC-7F19B411",
  status: "nouveau",
  priority: 80.1,
  priority_level: "critique",
  reason: "règle 2 : escalade_prioritaire",
  summary: "Intention : lost_stolen (88 %).",
  created_at: "2026-11-18T10:00:00Z",
  taken_at: null,
  closed_at: null,
  advisor: null,
  intent: "lost_stolen",
  script: "arabic",
  corrected_intent: null,
};

function detail(status: EscalationOut["status"], advisor: string | null): EscalationDetail {
  return {
    ...ITEM,
    status,
    advisor,
    priority_contributions: { urgence: 50, needs_human: 2.7, incertitude: 2.4, bonus: 25 },
    message: {
      id: "m-1",
      turn: 1,
      created_at: ITEM.created_at,
      text: "تسرق ليا التيليفون، النمرة <TEL>",
      script: "arabic",
      intent: "lost_stolen",
      category: "sim_line",
      product: "mobile",
      urgency: 3,
      needs_human: false,
      confidence: 0.88,
      decision_rule: 2,
      decision_action: "escalade",
      reply: "فهمتك، غادي نحولك لمستشار بالأولوية.",
      sources: [{ id: "KB-lost_stolen", version: 1 }],
      fiche_id: "KB-lost_stolen",
    },
    analysis: null,
    proposed_fiche: {
      id: "KB-lost_stolen",
      version: 1,
      title: "Téléphone ou carte SIM perdu ou volé",
      etapes: ["Demander immédiatement le blocage de la ligne."],
      escalade: "Cas sensible traité en priorité par un conseiller.",
    },
    history: [],
  };
}

function renderAs(role: "conseiller" | "admin") {
  writeJson("session", "darijacare.staff", {
    username: `${role}1`,
    role,
    token: `jeton-${role}`,
    expiresAt: Date.now() + 15 * 60 * 1000,
  });
  return render(
    <MemoryRouter>
      <AuthProvider>
        <ConsolePage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("ConsolePage", () => {
  beforeEach(() => resetIntentsCache());

  it("lists the queue, opens a case and takes it", async () => {
    let current = detail("nouveau", null);
    const calls = mockFetch({
      "GET /intents": () => json([]),
      "GET /escalades": () => json([{ ...ITEM, status: current.status, advisor: current.advisor }]),
      "GET /escalades/e-1": () => json(current),
      "PATCH /escalades/e-1": () => {
        current = detail("en_cours", "conseiller1");
        return json({ ...ITEM, status: "en_cours", advisor: "conseiller1" });
      },
    });
    const user = userEvent.setup();
    renderAs("conseiller");
    await user.click(await screen.findByRole("button", { name: /DC-7F19B411/ }));
    expect(
      await screen.findByText("Téléphone ou carte SIM perdu ou volé", { exact: false }),
    ).toBeInTheDocument();
    expect(screen.getByText("تسرق ليا التيليفون، النمرة <TEL>")).toBeInTheDocument();
    expect(screen.getByText("Bonus (sécurité, argent)")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Prendre en charge" }));
    expect(await screen.findByRole("button", { name: "Clôturer le dossier" })).toBeInTheDocument();
    const patch = calls.find((c) => c.method === "PATCH");
    expect(patch?.body).toEqual({ action: "prendre", corrected_intent: null });
    expect(patch?.headers.authorization).toBe("Bearer jeton-conseiller");
    expect(calls.find((c) => c.path.startsWith("/escalades?"))?.path).toContain(
      "status=nouveau&status=en_cours",
    );
  });

  it("is read-only for an administrator", async () => {
    mockFetch({
      "GET /intents": () => json([]),
      "GET /escalades": () => json([ITEM]),
      "GET /escalades/e-1": () => json(detail("nouveau", null)),
    });
    const user = userEvent.setup();
    renderAs("admin");
    expect(await screen.findByText(/Lecture seule/)).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: /DC-7F19B411/ }));
    await screen.findByText(/Téléphone ou carte SIM perdu ou volé/);
    expect(screen.queryByRole("button", { name: "Prendre en charge" })).toBeNull();
  });
});
