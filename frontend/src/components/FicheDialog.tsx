// Fiche citée en source, affichée dans une fenêtre accessible (Échap ferme, focus géré).
import { useEffect, useRef, useState } from "react";

import { api, ApiError } from "../api/client";
import type { FicheView, Lang } from "../api/types";

export default function FicheDialog({
  ficheId,
  lang,
  onClose,
}: {
  ficheId: string;
  lang: Lang;
  onClose: () => void;
}) {
  const [fiche, setFiche] = useState<FicheView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    api<FicheView>(`/fiches/${encodeURIComponent(ficheId)}?lang=${lang}`, {
      signal: controller.signal,
    })
      .then(setFiche)
      .catch((e: unknown) => {
        if (e instanceof ApiError) setError(e.message);
      });
    return () => controller.abort();
  }, [ficheId, lang]);

  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      previous?.focus();
    };
  }, [onClose]);

  const dir = lang === "ar" ? "rtl" : "ltr";
  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-nuit/60 p-0 sm:items-center sm:p-4"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="fiche-titre"
        className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-t-carte bg-white p-5 shadow-xl sm:rounded-carte"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4">
          <h2 id="fiche-titre" className="text-lg font-bold text-profond" dir={dir}>
            {fiche ? fiche.title : ficheId}
          </h2>
          <button ref={closeRef} type="button" className="bouton-secondaire" onClick={onClose}>
            Fermer
          </button>
        </div>
        {error && <p className="mt-4 text-[#9B1C1C]">{error}</p>}
        {!fiche && !error && <p className="mt-4 text-texte-2">Chargement de la fiche…</p>}
        {fiche && (
          <div
            className="mt-4 space-y-4"
            dir={dir}
            lang={lang === "ar" ? "ar" : lang === "fr" ? "fr" : undefined}
          >
            <p className="rounded-bouton bg-[#FFF7D6] p-3 text-sm text-[#7A4B00]">{fiche.notice}</p>
            <p className="text-xs text-texte-2" dir="ltr">
              {fiche.id} · version {fiche.version} · statut {fiche.status}
            </p>
            <section>
              <h3 className="font-semibold text-profond">Objet</h3>
              <p>{fiche.sections.objet}</p>
            </section>
            <section>
              <h3 className="font-semibold text-profond">Étapes</h3>
              <ol className="list-decimal space-y-1 ps-6">
                {fiche.sections.etapes.map((step) => (
                  <li key={step}>{step}</li>
                ))}
              </ol>
            </section>
            <section>
              <h3 className="font-semibold text-profond">Conditions</h3>
              <ul className="list-disc space-y-1 ps-6">
                {fiche.sections.conditions.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </section>
            <section>
              <h3 className="font-semibold text-profond">Limites</h3>
              <ul className="list-disc space-y-1 ps-6">
                {fiche.sections.limites.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </section>
            <section>
              <h3 className="font-semibold text-profond">Escalade</h3>
              <p>{fiche.sections.escalade}</p>
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
