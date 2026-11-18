// Garde côté interface : redirige vers la connexion. Les droits réels sont vérifiés par
// l'API à chaque requête (Tableau 14) ; cette garde ne fait qu'éviter des pages vides.
import { Navigate, useLocation } from "react-router";

import type { Role } from "../api/types";
import { useAuth } from "../lib/auth";

const ROLE_LABELS: Record<Role, string> = {
  conseiller: "conseiller",
  ml: "ML / data",
  admin: "administrateur",
};

export default function RequireRole({
  roles,
  children,
}: {
  roles: Role[];
  children: React.ReactNode;
}) {
  const { user } = useAuth();
  const location = useLocation();
  if (!user) return <Navigate to="/connexion" replace state={{ from: location.pathname }} />;
  if (!roles.includes(user.role)) {
    return (
      <div className="carte p-6">
        <h1 className="titre-page">Accès réservé</h1>
        <p className="mt-2">
          Cette page est réservée aux rôles : {roles.map((r) => ROLE_LABELS[r]).join(", ")}. Vous
          êtes connecté avec le rôle {ROLE_LABELS[user.role]}.
        </p>
      </div>
    );
  }
  return <>{children}</>;
}
