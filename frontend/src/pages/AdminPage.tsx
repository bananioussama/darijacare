// Gestion de la base de connaissances et des modèles (Tableau 29) : fiches, modèles et
// évaluations, configuration de décision (lecture), comptes du personnel (administrateur).
import { useEffect, useState } from "react";

import { ApiError } from "../api/client";
import type { DecisionConfigOut, KbFiche, ModelInfo, Role, UserOut } from "../api/types";
import FicheDialog from "../components/FicheDialog";
import { useAuth, useStaffApi } from "../lib/auth";
import { formatDate } from "../lib/labels";
import { useTitle } from "../lib/useTitle";

const decimal = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 3 });

function UsersSection() {
  const call = useStaffApi();
  const [users, setUsers] = useState<UserOut[] | null>(null);
  const [form, setForm] = useState({ username: "", password: "", role: "conseiller" as Role });
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    call<UserOut[]>("/admin/users")
      .then(setUsers)
      .catch(() => setUsers([]));
  }, [call]);

  async function create(event: React.FormEvent): Promise<void> {
    event.preventDefault();
    setMessage(null);
    try {
      const user = await call<UserOut>("/admin/users", { method: "POST", body: form });
      setUsers((list) => [...(list ?? []), user]);
      setForm({ username: "", password: "", role: "conseiller" });
      setMessage({ ok: true, text: `Compte ${user.username} créé.` });
    } catch (e) {
      setMessage({ ok: false, text: e instanceof ApiError ? e.message : "Création impossible." });
    }
  }

  return (
    <section className="carte p-4" aria-labelledby="titre-comptes">
      <h2 id="titre-comptes" className="text-lg font-bold text-profond">
        Comptes du personnel
      </h2>
      <table className="mt-2 w-full text-sm">
        <thead>
          <tr className="text-texte-2">
            <th className="py-1 text-start font-normal">Identifiant</th>
            <th className="py-1 text-start font-normal">Rôle</th>
            <th className="py-1 text-start font-normal">Actif</th>
            <th className="py-1 text-start font-normal">Créé le</th>
          </tr>
        </thead>
        <tbody>
          {users?.map((u) => (
            <tr key={u.id} className="border-t border-lavande">
              <td className="py-1">{u.username}</td>
              <td className="py-1">{u.role}</td>
              <td className="py-1">{u.active ? "oui" : "non"}</td>
              <td className="py-1">{formatDate(u.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <form className="mt-4 grid gap-3 sm:grid-cols-4" onSubmit={(event) => void create(event)}>
        <div>
          <label htmlFor="nouvel-identifiant" className="block text-sm font-semibold">
            Identifiant
          </label>
          <input
            id="nouvel-identifiant"
            className="champ mt-1"
            dir="ltr"
            required
            minLength={3}
            pattern="[a-zA-Z0-9._\-]+"
            value={form.username}
            onChange={(e) => setForm({ ...form, username: e.target.value })}
          />
        </div>
        <div>
          <label htmlFor="nouveau-mot-de-passe" className="block text-sm font-semibold">
            Mot de passe (12 caractères min.)
          </label>
          <input
            id="nouveau-mot-de-passe"
            type="password"
            className="champ mt-1"
            dir="ltr"
            autoComplete="new-password"
            required
            minLength={12}
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
          />
        </div>
        <div>
          <label htmlFor="nouveau-role" className="block text-sm font-semibold">
            Rôle
          </label>
          <select
            id="nouveau-role"
            className="champ mt-1"
            value={form.role}
            onChange={(e) => setForm({ ...form, role: e.target.value as Role })}
          >
            <option value="conseiller">Conseiller</option>
            <option value="ml">ML / data</option>
            <option value="admin">Administrateur</option>
          </select>
        </div>
        <div className="flex items-end">
          <button type="submit" className="bouton-principal w-full">
            Créer le compte
          </button>
        </div>
      </form>
      {message && (
        <p
          className={`mt-2 text-sm ${message.ok ? "text-[#14532D]" : "text-[#9B1C1C]"}`}
          role={message.ok ? "status" : "alert"}
        >
          {message.text}
        </p>
      )}
    </section>
  );
}

export default function AdminPage() {
  useTitle("Base et modèles");
  const { user } = useAuth();
  const call = useStaffApi();
  const [fiches, setFiches] = useState<KbFiche[] | null>(null);
  const [models, setModels] = useState<ModelInfo[] | null>(null);
  const [config, setConfig] = useState<DecisionConfigOut | null>(null);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : "Erreur inattendue.");
    call<KbFiche[]>("/kb/fiches").then(setFiches).catch(fail);
    call<ModelInfo[]>("/models").then(setModels).catch(fail);
    call<DecisionConfigOut>("/config/decision").then(setConfig).catch(fail);
  }, [call]);

  const q = query.trim().toLowerCase();
  const shown = (fiches ?? []).filter(
    (f) => !q || f.id.toLowerCase().includes(q) || (f.titles.fr ?? "").toLowerCase().includes(q),
  );

  return (
    <div className="space-y-4">
      <h1 className="titre-page">Base de connaissances et modèles</h1>
      {error && (
        <p className="rounded-bouton bg-[#FDECEC] p-3 text-sm text-[#9B1C1C]" role="alert">
          {error}
        </p>
      )}

      <section className="carte p-4" aria-labelledby="titre-fiches">
        <div className="flex flex-wrap items-end justify-between gap-2">
          <h2 id="titre-fiches" className="text-lg font-bold text-profond">
            Fiches ({fiches?.length ?? "…"})
          </h2>
          <div>
            <label htmlFor="recherche-fiche" className="block text-sm font-semibold">
              Rechercher
            </label>
            <input
              id="recherche-fiche"
              className="champ mt-1 w-64"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
        </div>
        <p className="mt-1 text-sm text-texte-2">
          Fiches fictives en français, darija (écriture arabe) et arabizi. Elles se modifient dans
          kb/ (Markdown, relecture par l'équipe), puis s'indexent avec make rag-index.
        </p>
        <div className="mt-2 max-h-96 overflow-y-auto pe-1">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-white">
              <tr className="text-texte-2">
                <th className="py-1 text-start font-normal">Fiche</th>
                <th className="py-1 text-start font-normal">Titre</th>
                <th className="py-1 text-start font-normal">Version</th>
                <th className="py-1 text-start font-normal">Statut</th>
                <th className="py-1" />
              </tr>
            </thead>
            <tbody>
              {shown.map((f) => (
                <tr key={f.id} className="border-t border-lavande">
                  <td className="py-1" dir="ltr">
                    {f.id}
                  </td>
                  <td className="py-1">{f.titles.fr}</td>
                  <td className="py-1">v{f.version}</td>
                  <td className="py-1">{f.status}</td>
                  <td className="py-1 text-end">
                    <button
                      type="button"
                      className="bouton-secondaire"
                      onClick={() => setOpen(f.id)}
                    >
                      Voir
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="carte p-4" aria-labelledby="titre-modeles">
        <h2 id="titre-modeles" className="text-lg font-bold text-profond">
          Modèles NLU
        </h2>
        <table className="mt-2 w-full text-sm">
          <thead>
            <tr className="text-texte-2">
              <th className="py-1 text-start font-normal">Version</th>
              <th className="py-1 text-start font-normal">Encodeur</th>
              <th className="py-1 text-start font-normal">Statut</th>
              <th className="py-1 text-start font-normal">Évaluations</th>
            </tr>
          </thead>
          <tbody>
            {models?.map((m) => (
              <tr key={m.version} className="border-t border-lavande align-top">
                <td className="py-1" dir="ltr">
                  {m.version}
                </td>
                <td className="py-1" dir="ltr">
                  {m.encoder}
                </td>
                <td className="py-1">{m.status}</td>
                <td className="py-1">
                  {m.evaluations.length === 0
                    ? "—"
                    : m.evaluations.map((e) => (
                        <span key={e.source} className="block">
                          {e.dataset} : F1 macro{" "}
                          {e.f1_macro != null ? decimal.format(e.f1_macro) : "—"}, ECE{" "}
                          {e.ece != null ? decimal.format(e.ece) : "—"}
                        </span>
                      ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {config && (
        <section className="carte p-4" aria-labelledby="titre-config">
          <h2 id="titre-config" className="text-lg font-bold text-profond">
            Configuration de décision
          </h2>
          <p className="mt-1 text-sm text-texte-2">
            Empreinte {config.id}. Lecture seule : les seuils se modifient dans
            configs/decision.yaml (fichier versionné) ; chaque message enregistre l'empreinte de la
            configuration qui l'a traité.
          </p>
          <dl className="mt-2 grid gap-x-4 gap-y-1 text-sm sm:grid-cols-2">
            {Object.entries(config.content.thresholds).map(([name, value]) => (
              <div key={name} className="flex justify-between gap-2 border-b border-lavande py-1">
                <dt>Seuil {name}</dt>
                <dd className="font-semibold">{decimal.format(value)}</dd>
              </div>
            ))}
            {Object.entries(config.content.priority.weights).map(([name, value]) => (
              <div key={name} className="flex justify-between gap-2 border-b border-lavande py-1">
                <dt>Poids de priorité : {name}</dt>
                <dd className="font-semibold">{decimal.format(value)}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      {user?.role === "admin" && <UsersSection />}
      {open && <FicheDialog ficheId={open} lang="fr" onClose={() => setOpen(null)} />}
    </div>
  );
}
