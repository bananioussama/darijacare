// Stockage du navigateur, toujours protégé : en navigation privée ou si le stockage est
// bloqué, l'interface fonctionne quand même (la session ne survit simplement pas au
// rechargement de la page).

type Store = "local" | "session";

function storage(store: Store): Storage {
  return store === "local" ? window.localStorage : window.sessionStorage;
}

export function readJson<T>(store: Store, key: string, fallback: T): T {
  try {
    const raw = storage(store).getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function writeJson(store: Store, key: string, value: unknown): void {
  try {
    storage(store).setItem(key, JSON.stringify(value));
  } catch {
    // stockage indisponible : on continue sans persistance
  }
}

export function removeKey(store: Store, key: string): void {
  try {
    storage(store).removeItem(key);
  } catch {
    // idem
  }
}
