// Liste des 75 intentions, groupées par catégorie (correction client et conseiller).
import { useEffect, useState } from "react";

import { api, ApiError } from "../api/client";
import type { IntentInfo } from "../api/types";
import { CATEGORY_LABELS } from "../lib/labels";

let cache: Promise<IntentInfo[]> | null = null;

export function loadIntents(): Promise<IntentInfo[]> {
  cache ??= api<IntentInfo[]>("/intents").catch((error: unknown) => {
    cache = null;
    throw error;
  });
  return cache;
}

/** Vide le cache (tests). */
export function resetIntentsCache(): void {
  cache = null;
}

export function useIntents(): { intents: IntentInfo[] | null; error: string | null } {
  const [intents, setIntents] = useState<IntentInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    loadIntents()
      .then((list) => alive && setIntents(list))
      .catch((e: unknown) => alive && setError(e instanceof ApiError ? e.message : String(e)));
    return () => {
      alive = false;
    };
  }, []);
  return { intents, error };
}

export default function IntentSelect({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (intent: string) => void;
}) {
  const { intents, error } = useIntents();
  const groups = new Map<string, IntentInfo[]>();
  for (const item of intents ?? []) {
    groups.set(item.category, [...(groups.get(item.category) ?? []), item]);
  }
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-semibold">
        {label}
      </label>
      <select
        id={id}
        className="champ mt-1"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={!intents}
      >
        <option value="">{intents ? "— Choisir l'intention —" : "Chargement…"}</option>
        {[...groups.entries()].map(([category, items]) => (
          <optgroup key={category} label={CATEGORY_LABELS[category] ?? category}>
            {items.map((item) => (
              <option key={item.intent} value={item.intent}>
                {item.titles.fr} ({item.intent})
              </option>
            ))}
          </optgroup>
        ))}
      </select>
      {error && <p className="mt-1 text-sm text-[#9B1C1C]">{error}</p>}
    </div>
  );
}
