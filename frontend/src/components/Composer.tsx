// Zone de saisie multiligne à orientation automatique (F-UI-01) : 4 à 500 caractères,
// Entrée envoie, Maj+Entrée va à la ligne.
import { useState } from "react";

import { MAX_CHARS, MIN_CHARS } from "../lib/labels";

export default function Composer({
  disabled,
  onSend,
}: {
  disabled: boolean;
  onSend: (text: string) => void;
}) {
  const [text, setText] = useState("");
  const length = text.trim().length;
  const valid = length >= MIN_CHARS && length <= MAX_CHARS;

  function submit(): void {
    if (!valid || disabled) return;
    onSend(text.trim());
    setText("");
  }

  return (
    <form
      className="flex items-end gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <div className="flex-1">
        <label htmlFor="message" className="sr-only">
          Votre message
        </label>
        <textarea
          id="message"
          dir="auto"
          rows={2}
          maxLength={MAX_CHARS}
          className="champ min-h-14 resize-y"
          placeholder="Écrivez en arabe, en arabizi ou en darija mêlée de français…"
          value={text}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault();
              submit();
            }
          }}
          aria-describedby="message-aide"
        />
        <p id="message-aide" className="mt-1 text-xs text-texte-2">
          {length > 0 && length < MIN_CHARS
            ? `${MIN_CHARS} caractères minimum.`
            : `${length}/${MAX_CHARS} · Entrée pour envoyer, Maj+Entrée pour aller à la ligne.`}
        </p>
      </div>
      <button
        type="submit"
        className="bouton-principal mb-6 min-w-11"
        disabled={!valid || disabled}
      >
        Envoyer
      </button>
    </form>
  );
}
