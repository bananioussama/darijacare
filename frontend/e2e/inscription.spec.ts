// Inscription du personnel (F-UI-08) sur la pile HTTPS : bouton « S'inscrire », demande en
// attente, validation ou refus par l'administrateur, puis connexion.
// Chaque lancement laisse un compte de test validé « e2e.inscrit.<horodatage> » (aucune route
// ne supprime un compte actif) ; la demande refusée, elle, est supprimée par le refus.
import { expect, test, type Page } from "@playwright/test";

const ADMIN = process.env.DARIJACARE_ADMIN_USERNAME ?? "";
const ADMIN_PASSWORD = process.env.DARIJACARE_ADMIN_PASSWORD ?? "";
const PASSWORD = "mot-de-passe-e2e-inscription";
const PENDING = "Compte en attente de validation par un administrateur.";

async function register(page: Page, username: string): Promise<void> {
  await page.goto("/");
  await page.getByRole("link", { name: "S'inscrire" }).click();
  await expect(page.getByRole("heading", { name: "Inscription du personnel" })).toBeVisible();
  await page.getByLabel("Identifiant").fill(username);
  await page.getByLabel("Mot de passe (12 caractères min.)").fill(PASSWORD);
  await page.getByLabel("Confirmer le mot de passe").fill(PASSWORD);
  await page.getByRole("button", { name: "Envoyer la demande" }).click();
  await expect(page.getByRole("heading", { name: "Demande envoyée" })).toBeVisible();
}

async function tryLogin(page: Page, username: string, password: string): Promise<void> {
  await page.goto("/connexion");
  await page.getByLabel("Identifiant").fill(username);
  await page.getByLabel("Mot de passe").fill(password);
  await page.getByRole("button", { name: "Se connecter" }).click();
}

test("inscription : demande en attente, validation par l'administrateur, puis connexion", async ({
  page,
  browser,
}) => {
  expect(ADMIN && ADMIN_PASSWORD, "compte administrateur requis (.env)").toBeTruthy();
  const stamp = Date.now();
  const accepted = `e2e.inscrit.${stamp}`;
  const refused = `e2e.refuse.${stamp}`;

  await register(page, accepted);
  await register(page, refused);
  await tryLogin(page, accepted, PASSWORD);
  await expect(page.getByRole("alert")).toHaveText(PENDING);

  const admin = await browser.newPage();
  await tryLogin(admin, ADMIN, ADMIN_PASSWORD);
  await expect(admin.getByRole("heading", { name: "Tableau de bord" })).toBeVisible();
  await admin.goto("/administration");
  const requests = admin.getByRole("region", { name: /Demandes d'inscription en attente/ });
  await expect(requests.getByText(accepted)).toBeVisible();
  await admin.getByRole("button", { name: `Valider l'inscription de ${accepted}` }).click();
  await expect(admin.getByText(`Compte ${accepted} validé (Conseiller)`)).toBeVisible();
  await admin.getByRole("button", { name: `Refuser l'inscription de ${refused}` }).click();
  await expect(admin.getByText(`Demande de ${refused} refusée et supprimée.`)).toBeVisible();

  await expect(requests.getByText(refused)).toHaveCount(0);
  await admin.close();

  // Le compte validé se connecte et arrive sur sa page de conseiller.
  await tryLogin(page, accepted, PASSWORD);
  await expect(page.getByRole("heading", { name: "Console conseiller" })).toBeVisible();

  // Trois connexions ici, une dans global-setup : on laisse passer la fenêtre de la limite de
  // l'API (5 connexions par minute et par adresse) avant les parcours suivants.
  await page.waitForTimeout(61_000);
});
