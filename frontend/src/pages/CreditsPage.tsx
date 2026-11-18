// Crédits (Tableau 29, licence CC BY 4.0) : attribution du jeu de données et des modèles.
import { useTitle } from "../lib/useTitle";

const MODELS = [
  {
    name: "mballouch/jev-darija-telecom-model (v5)",
    url: "https://huggingface.co/mballouch/jev-darija-telecom-model",
    role: "Modèle NLU servi, entraîné par l'auteur sur les 40 357 messages",
    license: "Apache 2.0",
  },
  {
    name: "mballouch/jev-darija-telecom-model (v3)",
    url: "https://huggingface.co/mballouch/jev-darija-telecom-model",
    role: "Référence historique, reproduite pour comparaison",
    license: "Apache 2.0",
  },
  {
    name: "mballouch/jev-darija",
    url: "https://huggingface.co/mballouch/jev-darija",
    role: "Point de départ du ré-entraînement",
    license: "non déclarée sur le Hub (usage académique)",
  },
  {
    name: "Laya multilingual (Convai Innovations)",
    url: "https://huggingface.co/convaiinnovations/laya",
    role: "Modèle de base ; bibliothèque laya",
    license: "Apache 2.0",
  },
  {
    name: "mmBERT (jhu-clsp/mmBERT-base)",
    url: "https://arxiv.org/abs/2509.06888",
    role: "Encodeur de Laya multilingual",
    license: "MIT",
  },
  {
    name: "BGE-M3 (BAAI)",
    url: "https://huggingface.co/BAAI/bge-m3",
    role: "Embeddings dense et creux de la base de connaissances",
    license: "MIT",
  },
];

export default function CreditsPage() {
  useTitle("Crédits");
  return (
    <div className="max-w-3xl space-y-4">
      <h1 className="titre-page">Crédits</h1>

      <section className="carte space-y-2 p-5" aria-labelledby="titre-donnees">
        <h2 id="titre-donnees" className="text-lg font-bold text-profond">
          Jeu de données
        </h2>
        <p>
          <cite>Jev-Darija Telecom: Moroccan Darija Customer-Service Messages</cite>, Mohamed
          Ballouch (2026),{" "}
          <a
            className="text-vif underline"
            href="https://huggingface.co/datasets/mballouch/jev-darija-telecom"
          >
            huggingface.co/datasets/mballouch/jev-darija-telecom
          </a>
          , sous licence{" "}
          <a
            className="text-vif underline"
            href="https://creativecommons.org/licenses/by/4.0/deed.fr"
          >
            Creative Commons Attribution 4.0 International (CC BY 4.0)
          </a>
          .
        </p>
        <p className="text-sm text-texte-2">
          Données synthétiques générées par des modèles de langage, non relues par des locuteurs
          natifs. Révision utilisée : 2d5de707e8a902b371f5925224f255984c3b34bc.
        </p>
        <h3 className="font-semibold">Modifications apportées par DarijaCare</h3>
        <ol className="list-decimal space-y-1 ps-6 text-sm">
          <li>
            Dédoublonnage : 2 paires de messages identiques aux intentions divergentes retirées.
          </li>
          <li>
            Normalisation : colonne text_norm ajoutée (le texte d'origine est conservé), numéros,
            liens et adresses masqués.
          </li>
          <li>
            Découpage : validation de 10 % tirée du train officiel ; le test officiel est inchangé.
          </li>
        </ol>
      </section>

      <section className="carte p-5" aria-labelledby="titre-modeles-credits">
        <h2 id="titre-modeles-credits" className="text-lg font-bold text-profond">
          Modèles
        </h2>
        <ul className="mt-2 space-y-3">
          {MODELS.map((m) => (
            <li key={m.name}>
              <a className="font-semibold text-vif underline" href={m.url}>
                {m.name}
              </a>
              <p className="text-sm">{m.role}</p>
              <p className="text-sm text-texte-2">Licence : {m.license}</p>
            </li>
          ))}
        </ul>
        <p className="mt-3 text-sm text-texte-2">
          Auteur des modèles jev-darija : Mohamed Ballouch (2026). Les poids publiés ne sont pas
          modifiés.
        </p>
      </section>

      <section className="carte space-y-2 p-5" aria-labelledby="titre-logiciels">
        <h2 id="titre-logiciels" className="text-lg font-bold text-profond">
          Logiciels et contenu
        </h2>
        <p className="text-sm">
          Python, PyTorch, Transformers, FastAPI, SQLAlchemy, Alembic, PostgreSQL, Qdrant, React,
          Vite, Tailwind CSS, React Router, Recharts, polices Inter et Noto Sans Arabic : chacun
          sous sa licence open source (détails dans CREDITS.md).
        </p>
        <p className="text-sm">
          Les 75 fiches de la base de connaissances sont <strong>fictives</strong> : elles ne
          décrivent les procédures d'aucun opérateur réel et ne contiennent ni prix, ni numéro, ni
          engagement réels. Projet académique (PFA) : aucune intégration à un système réel.
        </p>
      </section>
    </div>
  );
}
