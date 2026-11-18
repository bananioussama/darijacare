import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";

import { AuthProvider } from "../lib/auth";
import { listSessions } from "../lib/sessions";
import { answerEvents, json, mockFetch, sse } from "../test/fetchMock";
import ChatPage from "./ChatPage";

function renderChat() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <ChatPage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("ChatPage", () => {
  it("streams the reply with sources, confidence, analysis and saves the session", async () => {
    const calls = mockFetch({ "POST /chat": () => sse(answerEvents()) });
    const user = userEvent.setup();
    renderChat();
    await user.type(screen.getByLabelText("Votre message"), "solde dyali 0612345678{Enter}");

    const reply = await screen.findByLabelText("Réponse de l'assistant");
    await within(reply).findByText(/Chouf solde\./);
    expect(within(reply).getByText("Réponse automatique")).toBeInTheDocument();
    expect(within(reply).getByText("Confiance élevée · 90 %")).toBeInTheDocument();
    expect(within(reply).getByText("KB-balance_check · v1")).toBeInTheDocument();
    expect(within(reply).getByText("Nchouf solde")).toBeInTheDocument();
    expect(within(reply).getByRole("button", { name: "Utile" })).toBeInTheDocument();

    const panel = screen.getByRole("complementary", { name: "Analyse NLU" });
    expect(within(panel).getAllByText("balance_check").length).toBeGreaterThan(0);
    expect(within(panel).getByText("Crédit prépayé")).toBeInTheDocument();
    expect(within(panel).getByText(/Règle 7/)).toBeInTheDocument();

    expect(calls[0]).toMatchObject({
      method: "POST",
      path: "/chat",
      body: { text: "solde dyali 0612345678", request_human: false },
    });
    expect(calls[0]?.headers.authorization).toBeUndefined();
    expect(listSessions()[0]).toMatchObject({ session_id: "s-1", token: "jeton-session-1" });
  });

  it("sends the session token on the next message and the advisor request flag", async () => {
    const calls = mockFetch({ "POST /chat": () => sse(answerEvents()) });
    const user = userEvent.setup();
    renderChat();
    await user.type(screen.getByLabelText("Votre message"), "solde dyali{Enter}");
    await screen.findByText("KB-balance_check · v1");
    await user.click(screen.getByRole("button", { name: "Parler à un conseiller" }));
    await screen.findAllByText("KB-balance_check · v1");
    expect(calls[1]).toMatchObject({
      body: { text: "bghit nhder m3a chi conseiller", request_human: true },
    });
    expect(calls[1]?.headers.authorization).toBe("Bearer jeton-session-1");
  });

  it("renders a hostile reply as text, never as HTML", async () => {
    mockFetch({ "POST /chat": () => sse(answerEvents('<img src="x" onerror="alert(1)"> salam')) });
    const user = userEvent.setup();
    const { container } = renderChat();
    await user.type(screen.getByLabelText("Votre message"), "solde dyali{Enter}");
    await screen.findByText(/<img src="x" onerror="alert\(1\)"> salam/);
    expect(container.querySelector("img")).toBeNull();
  });

  it("lets the analysis panel be hidden and shows API errors", async () => {
    mockFetch({
      "POST /chat": () => json({ detail: "Trop de requêtes, réessayez dans un instant." }, 429),
    });
    const user = userEvent.setup();
    renderChat();
    await user.click(screen.getByRole("button", { name: "Masquer l'analyse" }));
    expect(screen.queryByRole("complementary", { name: "Analyse NLU" })).toBeNull();
    await user.type(screen.getByLabelText("Votre message"), "solde dyali{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent("Trop de requêtes");
  });

  it("refuses to send fewer than 4 characters", async () => {
    const calls = mockFetch({});
    const user = userEvent.setup();
    renderChat();
    await user.type(screen.getByLabelText("Votre message"), "ok{Enter}");
    expect(screen.getByText("4 caractères minimum.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Envoyer" })).toBeDisabled();
    expect(calls).toHaveLength(0);
  });

  it("starts from a clickable example in the customer's script", async () => {
    const calls = mockFetch({ "POST /chat": () => sse(answerEvents()) });
    const user = userEvent.setup();
    renderChat();
    await user.click(screen.getByRole("button", { name: /الكونيكسيون مقطوعة/ }));
    await screen.findByText("KB-balance_check · v1");
    expect(calls[0]?.body).toMatchObject({ text: "الكونيكسيون مقطوعة من البارح ف الدار" });
  });
});
