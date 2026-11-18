// Connexion du personnel (F-UI-08) : conseiller, ML / data, administrateur.
import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";

import { ApiError } from "../api/client";
import { homeOf, useAuth } from "../lib/auth";
import { useTitle } from "../lib/useTitle";

export default function LoginPage() {
  useTitle("Connexion");
  const { login, notice, user } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from;
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) {
    return (
      <div className="carte mx-auto max-w-md p-6">
        <h1 className="titre-page">Connecté</h1>
        <p className="mt-2">
          Vous êtes connecté en tant que <strong>{user.username}</strong>.
        </p>
        <Link to={homeOf(user.role)} className="bouton-principal mt-4">
          Continuer
        </Link>
      </div>
    );
  }

  async function submit(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const signedIn = await login(username.trim(), password);
      navigate(from && from !== "/connexion" ? from : homeOf(signedIn.role), { replace: true });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Connexion impossible.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="carte mx-auto max-w-md p-6">
      <h1 className="titre-page">Connexion du personnel</h1>
      <p className="mt-1 text-sm text-texte-2">
        Réservée aux conseillers, à l'équipe ML / data et aux administrateurs. La session dure 15
        minutes.
      </p>
      {notice && (
        <p className="mt-3 rounded-bouton bg-[#FFF7D6] p-3 text-sm text-[#7A4B00]" role="status">
          {notice}
        </p>
      )}
      <form className="mt-4 space-y-4" onSubmit={(event) => void submit(event)}>
        <div>
          <label htmlFor="identifiant" className="block text-sm font-semibold">
            Identifiant
          </label>
          <input
            id="identifiant"
            className="champ mt-1"
            dir="ltr"
            autoComplete="username"
            required
            value={username}
            onChange={(event) => setUsername(event.target.value)}
          />
        </div>
        <div>
          <label htmlFor="mot-de-passe" className="block text-sm font-semibold">
            Mot de passe
          </label>
          <input
            id="mot-de-passe"
            type="password"
            className="champ mt-1"
            dir="ltr"
            autoComplete="current-password"
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>
        {error && (
          <p className="text-sm text-[#9B1C1C]" role="alert">
            {error}
          </p>
        )}
        <button type="submit" className="bouton-principal w-full" disabled={busy}>
          {busy ? "Connexion…" : "Se connecter"}
        </button>
      </form>
    </div>
  );
}
