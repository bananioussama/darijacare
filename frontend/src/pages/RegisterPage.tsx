// Inscription du personnel (F-UI-08) : la demande reste en attente jusqu'à ce qu'un
// administrateur la valide et choisisse le rôle. Les clients n'ont pas de compte.
import { useState } from "react";
import { Link } from "react-router";

import { api, ApiError } from "../api/client";
import type { RegisterOut } from "../api/types";
import { homeOf, useAuth } from "../lib/auth";
import { useTitle } from "../lib/useTitle";

type RequestedRole = "conseiller" | "ml";

const EMPTY = { username: "", password: "", confirm: "", role: "conseiller" as RequestedRole };

function explain(error: unknown): string {
  if (!(error instanceof ApiError)) return "Inscription impossible.";
  if (error.status === 422) {
    return (
      "Vérifiez l'identifiant (3 à 64 caractères : lettres, chiffres, point, tiret, tiret bas) " +
      "et le mot de passe (12 caractères minimum)."
    );
  }
  return error.message;
}

export default function RegisterPage() {
  useTitle("Inscription");
  const { user } = useAuth();
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) {
    return (
      <div className="carte mx-auto max-w-md p-6">
        <h1 className="titre-page">Déjà connecté</h1>
        <p className="mt-2">
          Vous êtes connecté en tant que <strong>{user.username}</strong>.
        </p>
        <Link to={homeOf(user.role)} className="bouton-principal mt-4">
          Continuer
        </Link>
      </div>
    );
  }

  if (done) {
    return (
      <div className="carte mx-auto max-w-md p-6">
        <h1 className="titre-page">Demande envoyée</h1>
        <p className="mt-2" role="status">
          {done}
        </p>
        <Link to="/connexion" className="bouton-principal mt-4 w-full">
          Aller à la connexion
        </Link>
      </div>
    );
  }

  async function submit(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    setError(null);
    if (form.password !== form.confirm) {
      setError("Les deux mots de passe ne correspondent pas.");
      return;
    }
    setBusy(true);
    try {
      const out = await api<RegisterOut>("/auth/register", {
        method: "POST",
        body: {
          username: form.username.trim(),
          password: form.password,
          requested_role: form.role,
        },
      });
      setForm(EMPTY);
      setDone(out.detail);
    } catch (e) {
      setError(explain(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="carte mx-auto max-w-md p-6">
      <h1 className="titre-page">Inscription du personnel</h1>
      <p className="mt-1 text-sm text-texte-2">
        Pour les conseillers et l'équipe ML / data. Un administrateur examine la demande, active le
        compte et confirme le rôle ; vous pourrez ensuite vous connecter. Les clients n'ont pas
        besoin de compte pour utiliser l'assistant.
      </p>
      <form className="mt-4 space-y-4" onSubmit={(event) => void submit(event)}>
        <div>
          <label htmlFor="inscription-identifiant" className="block text-sm font-semibold">
            Identifiant
          </label>
          <input
            id="inscription-identifiant"
            className="champ mt-1"
            dir="ltr"
            autoComplete="username"
            required
            minLength={3}
            maxLength={64}
            pattern="[a-zA-Z0-9._\-]+"
            aria-describedby="inscription-identifiant-aide"
            value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })}
          />
          <p id="inscription-identifiant-aide" className="mt-1 text-xs text-texte-2">
            3 à 64 caractères : lettres, chiffres, point, tiret, tiret bas.
          </p>
        </div>
        <div>
          <label htmlFor="inscription-mot-de-passe" className="block text-sm font-semibold">
            Mot de passe (12 caractères min.)
          </label>
          <input
            id="inscription-mot-de-passe"
            type="password"
            className="champ mt-1"
            dir="ltr"
            autoComplete="new-password"
            required
            minLength={12}
            maxLength={256}
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
        </div>
        <div>
          <label htmlFor="inscription-confirmation" className="block text-sm font-semibold">
            Confirmer le mot de passe
          </label>
          <input
            id="inscription-confirmation"
            type="password"
            className="champ mt-1"
            dir="ltr"
            autoComplete="new-password"
            required
            minLength={12}
            maxLength={256}
            value={form.confirm}
            onChange={(e) => setForm({ ...form, confirm: e.target.value })}
          />
        </div>
        <div>
          <label htmlFor="inscription-role" className="block text-sm font-semibold">
            Rôle demandé
          </label>
          <select
            id="inscription-role"
            className="champ mt-1"
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value as RequestedRole })}
          >
            <option value="conseiller">Conseiller</option>
            <option value="ml">ML / data</option>
          </select>
        </div>
        {error && (
          <p className="text-sm text-[#9B1C1C]" role="alert">
            {error}
          </p>
        )}
        <button type="submit" className="bouton-principal w-full" disabled={busy}>
          {busy ? "Envoi…" : "Envoyer la demande"}
        </button>
      </form>
      <p className="mt-4 text-center text-sm text-texte-2">
        Déjà un compte ?{" "}
        <Link to="/connexion" className="font-semibold text-vif underline">
          Se connecter
        </Link>
      </p>
    </div>
  );
}
