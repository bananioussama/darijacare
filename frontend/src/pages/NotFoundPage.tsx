import { Link } from "react-router";

import { useTitle } from "../lib/useTitle";

export default function NotFoundPage() {
  useTitle("Page introuvable");
  return (
    <div className="carte mx-auto max-w-md p-6">
      <h1 className="titre-page">Page introuvable</h1>
      <p className="mt-2">Cette adresse ne correspond à aucune page.</p>
      <Link to="/" className="bouton-principal mt-4">
        Retour à l'assistant
      </Link>
    </div>
  );
}
