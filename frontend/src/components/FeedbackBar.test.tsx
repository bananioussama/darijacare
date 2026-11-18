import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { json, mockFetch } from "../test/fetchMock";
import FeedbackBar from "./FeedbackBar";
import { resetIntentsCache } from "./IntentSelect";

const INTENTS = [
  {
    intent: "balance_check",
    category: "prepaid_credit",
    titles: { fr: "Consulter son solde", ar: "نشوف الصولد", arabizi: "Nchouf solde" },
  },
  {
    intent: "balance_deducted",
    category: "prepaid_credit",
    titles: { fr: "Crédit qui diminue", ar: "الصولد كينقص", arabizi: "Solde kayn9es" },
  },
];

describe("FeedbackBar", () => {
  beforeEach(() => resetIntentsCache());

  it("sends « utile » with the session token", async () => {
    const calls = mockFetch({ "POST /feedback": () => json({}, 201) });
    const user = userEvent.setup();
    render(<FeedbackBar messageId="m-1" token="jeton" />);
    await user.click(screen.getByRole("button", { name: "Utile" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Merci");
    expect(calls[0]).toMatchObject({
      method: "POST",
      path: "/feedback",
      body: { message_id: "m-1", rating: "utile", corrected_intent: null, comment: null },
    });
    expect(calls[0]?.headers.authorization).toBe("Bearer jeton");
  });

  it("« Corriger » opens the intent list and sends the correction", async () => {
    const calls = mockFetch({
      "GET /intents": () => json(INTENTS),
      "POST /feedback": () => json({}, 201),
    });
    const user = userEvent.setup();
    render(<FeedbackBar messageId="m-1" token="jeton" />);
    await user.click(screen.getByRole("button", { name: "Corriger" }));
    const select = await screen.findByLabelText("Quelle était la bonne intention ?");
    await screen.findByRole("option", { name: /Crédit qui diminue/ });
    await user.selectOptions(select, "balance_deducted");
    await user.type(screen.getByLabelText("Commentaire (facultatif)"), "machi hadi");
    await user.click(screen.getByRole("button", { name: "Envoyer la correction" }));
    expect(await screen.findByRole("status")).toHaveTextContent("correction enregistrée");
    expect(calls.at(-1)?.body).toEqual({
      message_id: "m-1",
      rating: "a_corriger",
      corrected_intent: "balance_deducted",
      comment: "machi hadi",
    });
  });
});
