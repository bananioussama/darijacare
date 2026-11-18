// Boutons « Utile » / « Corriger » (F-UI-04) : la correction ouvre la liste des intentions.
import { useState } from "react";

import { api, ApiError } from "../api/client";
import IntentSelect from "./IntentSelect";

type State = "idle" | "correcting" | "sending" | "sent";

export default function FeedbackBar({
  messageId,
  token,
}: {
  messageId: string;
  token: string | null;
}) {
  const [state, setState] = useState<State>("idle");
  const [intent, setIntent] = useState("");
  const [comment, setComment] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [thanks, setThanks] = useState("");

  async function send(rating: "utile" | "a_corriger"): Promise<void> {
    setState("sending");
    setError(null);
    try {
      await api("/feedback", {
        method: "POST",
        token,
        body: {
          message_id: messageId,
          rating,
          corrected_intent: rating === "a_corriger" && intent ? intent : null,
          comment: rating === "a_corriger" && comment.trim() ? comment.trim() : null,
        },
      });
      setThanks(
        rating === "utile" ? "Merci, réponse notée utile." : "Merci, correction enregistrée.",
      );
      setState("sent");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Envoi impossible.");
      setState(rating === "a_corriger" ? "correcting" : "idle");
    }
  }

  if (state === "sent") {
    return (
      <p className="mt-3 text-sm text-[#14532D]" role="status">
        {thanks}
      </p>
    );
  }
  return (
    <div className="mt-3">
      {state !== "correcting" && (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="bouton bg-[#E6F6EC] text-[#14532D] ring-1 ring-[#14532D]/40 hover:bg-[#d3efdd]"
            onClick={() => void send("utile")}
            disabled={state === "sending"}
          >
            Utile
          </button>
          <button
            type="button"
            className="bouton bg-[#FFF1E0] text-[#8A3B00] ring-1 ring-[#8A3B00]/40 hover:bg-[#ffe6c7]"
            onClick={() => setState("correcting")}
            disabled={state === "sending"}
          >
            Corriger
          </button>
        </div>
      )}
      {state === "correcting" && (
        <form
          className="mt-2 space-y-3 rounded-bouton bg-gris p-3"
          onSubmit={(event) => {
            event.preventDefault();
            void send("a_corriger");
          }}
        >
          <IntentSelect
            id={`correction-${messageId}`}
            label="Quelle était la bonne intention ?"
            value={intent}
            onChange={setIntent}
          />
          <div>
            <label htmlFor={`commentaire-${messageId}`} className="block text-sm font-semibold">
              Commentaire (facultatif)
            </label>
            <textarea
              id={`commentaire-${messageId}`}
              className="champ mt-1"
              dir="auto"
              rows={2}
              maxLength={1000}
              value={comment}
              onChange={(event) => setComment(event.target.value)}
            />
            <p className="mt-1 text-xs text-texte-2">
              Les numéros, adresses e-mail et liens sont masqués avant enregistrement.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button type="submit" className="bouton-principal">
              Envoyer la correction
            </button>
            <button type="button" className="bouton-secondaire" onClick={() => setState("idle")}>
              Annuler
            </button>
          </div>
        </form>
      )}
      {error && (
        <p className="mt-2 text-sm text-[#9B1C1C]" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
