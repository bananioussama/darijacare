// Encart « Sources » (F-UI-03) : fiches citées (identifiant, version, titre), consultables.
import { useState } from "react";

import type { Lang, Source } from "../api/types";
import FicheDialog from "./FicheDialog";

export default function SourcesBox({ sources, lang }: { sources: Source[]; lang: Lang }) {
  const [open, setOpen] = useState<string | null>(null);
  if (sources.length === 0) return null;
  return (
    <div className="mt-3">
      <h3 className="text-sm font-semibold text-profond">Sources</h3>
      <ul className="mt-1 flex flex-wrap gap-2">
        {sources.map((source) => (
          <li key={source.id}>
            <button
              type="button"
              className="inline-flex min-h-11 flex-col items-start gap-0.5 rounded-bouton bg-white px-3 py-2 text-start text-sm text-profond ring-1 ring-vif transition-colors hover:bg-lavande sm:flex-row sm:items-center sm:gap-2"
              onClick={() => setOpen(source.id)}
            >
              {/* Nom accessible = texte visible précédé de l'action (WCAG 2.5.3). */}
              <span className="sr-only">Ouvrir la fiche </span>
              <span className="font-semibold whitespace-nowrap" dir="ltr">
                {source.id} · v{source.version}
              </span>
              {source.title && (
                <span className="text-texte-2" dir="auto">
                  {source.title}
                </span>
              )}
            </button>
          </li>
        ))}
      </ul>
      {open && <FicheDialog ficheId={open} lang={lang} onClose={() => setOpen(null)} />}
    </div>
  );
}
