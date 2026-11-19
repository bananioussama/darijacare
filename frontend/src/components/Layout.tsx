// Coquille de l'application : barre latérale violet nuit (maquettes Figures 12 et 13),
// menu repliable sur mobile, lien d'évitement vers le contenu.
import { useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router";

import type { Role } from "../api/types";
import { useAuth } from "../lib/auth";

interface NavItem {
  to: string;
  label: string;
  roles: Role[] | null;
}

const NAV: NavItem[] = [
  { to: "/", label: "Assistant", roles: null },
  { to: "/historique", label: "Historique de session", roles: null },
  { to: "/console", label: "Console conseiller", roles: ["conseiller", "admin"] },
  { to: "/tableau-de-bord", label: "Tableau de bord", roles: ["conseiller", "ml", "admin"] },
  { to: "/administration", label: "Base et modèles", roles: ["ml", "admin"] },
  { to: "/credits", label: "Crédits", roles: null },
];

const ROLE_LABELS: Record<Role, string> = {
  conseiller: "Conseiller",
  ml: "ML / data",
  admin: "Administrateur",
};

export default function Layout() {
  const { user, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const location = useLocation();
  const items = NAV.filter(
    (item) => item.roles === null || (user && item.roles.includes(user.role)),
  );

  const nav = (
    <nav aria-label="Navigation principale" className="flex flex-1 flex-col gap-1">
      {items.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.to === "/"}
          onClick={() => setMenuOpen(false)}
          className={({ isActive }) =>
            `flex min-h-11 items-center rounded-bouton px-3 text-sm font-semibold focus-visible:outline-lumineux ${
              isActive ? "bg-vif text-white" : "text-lavande hover:bg-profond"
            }`
          }
        >
          {item.label}
        </NavLink>
      ))}
      <div className="mt-auto space-y-2 border-t border-profond pt-4 text-sm text-lavande">
        {user ? (
          <>
            <p>
              <span className="font-semibold text-white">{user.username}</span>
              <br />
              {ROLE_LABELS[user.role]}
            </p>
            <button
              type="button"
              className="bouton w-full bg-profond text-white hover:bg-vif focus-visible:outline-lumineux"
              onClick={() => logout()}
            >
              Se déconnecter
            </button>
          </>
        ) : (
          <>
            <NavLink
              to="/connexion"
              state={{ from: location.pathname }}
              onClick={() => setMenuOpen(false)}
              className="flex min-h-11 items-center rounded-bouton px-3 font-semibold text-lavande hover:bg-profond focus-visible:outline-lumineux"
            >
              Connexion du personnel
            </NavLink>
            <NavLink
              to="/inscription"
              onClick={() => setMenuOpen(false)}
              className="flex min-h-11 items-center justify-center rounded-bouton px-3 font-semibold text-white ring-1 ring-lumineux hover:bg-profond focus-visible:outline-lumineux"
            >
              S'inscrire
            </NavLink>
          </>
        )}
        <p className="text-xs leading-relaxed">
          Projet académique : données synthétiques, fiches fictives, aucun système réel.
        </p>
      </div>
    </nav>
  );

  return (
    <div className="flex min-h-dvh flex-col lg:flex-row">
      <a
        href="#contenu"
        className="sr-only z-50 rounded-bouton bg-white p-3 focus:not-sr-only focus:fixed focus:start-2 focus:top-2"
      >
        Aller au contenu
      </a>
      <header className="flex items-center justify-between bg-nuit px-4 py-2 lg:hidden">
        <span className="text-lg font-bold text-white">DarijaCare</span>
        <button
          type="button"
          className="bouton bg-profond text-white focus-visible:outline-lumineux"
          aria-expanded={menuOpen}
          aria-controls="menu-mobile"
          onClick={() => setMenuOpen((open) => !open)}
        >
          {menuOpen ? "Fermer le menu" : "Menu"}
        </button>
      </header>
      {menuOpen && (
        <div id="menu-mobile" className="flex flex-col bg-nuit p-4 lg:hidden">
          {nav}
        </div>
      )}
      <aside className="hidden w-64 shrink-0 flex-col gap-6 bg-nuit p-5 lg:flex">
        <p className="text-xl font-bold text-white">DarijaCare</p>
        {nav}
      </aside>
      <main id="contenu" tabIndex={-1} className="min-w-0 flex-1 p-4 lg:p-6">
        <Outlet />
      </main>
    </div>
  );
}
