// Parcours de bout en bout (cahier des charges, Tableau 35 : chat, analyse, console,
// tableau de bord), avec les vrais modèles, via le frontal HTTPS de la pile Docker.
import { expect, test, type Locator, type Page } from "@playwright/test";

import { ADVISOR } from "./global-setup";

const ADMIN = process.env.DARIJACARE_ADMIN_USERNAME ?? "";
const ADMIN_PASSWORD = process.env.DARIJACARE_ADMIN_PASSWORD ?? "";
const ADVISOR_PASSWORD = process.env.DARIJACARE_E2E_PASSWORD ?? "";
const MODEL_TIMEOUT = 90_000;

test.describe.configure({ mode: "serial" });

/** Erreurs du navigateur et boîtes de dialogue (une alerte trahirait un script injecté). */
function watch(page: Page): string[] {
  const problems: string[] = [];
  page.on("pageerror", (e) => problems.push(e.message));
  page.on("dialog", (d) => {
    problems.push(`dialogue inattendu : ${d.message()}`);
    void d.dismiss();
  });
  return problems;
}

const answers = (page: Page): Locator => page.locator("article[aria-busy='false']");

async function send(page: Page, text: string): Promise<Locator> {
  const before = await answers(page).count();
  await page.getByLabel("Votre message").fill(text);
  await page.getByLabel("Votre message").press("Enter");
  const answer = answers(page).nth(before);
  await expect(answer).toBeVisible({ timeout: MODEL_TIMEOUT });
  return answer;
}

async function login(page: Page, username: string, password: string, heading: string) {
  await page.goto("/connexion");
  await page.getByLabel("Identifiant").fill(username);
  await page.getByLabel("Mot de passe").fill(password);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page.getByRole("heading", { name: heading })).toBeVisible();
}

let caseNumber = "";

test("chat : exemple cliquable, réponse en flux, sources, analyse NLU, retour « Utile »", async ({
  page,
}) => {
  const problems = watch(page);
  await page.goto("/");
  await page.getByRole("button", { name: /solde dyali sala/ }).click();
  const answer = answers(page).first();
  await expect(answer).toBeVisible({ timeout: MODEL_TIMEOUT });
  await expect(answer.getByText("Réponse automatique")).toBeVisible();
  await expect(answer.getByRole("heading", { name: "Sources" })).toBeVisible();
  const fiche = answer.getByRole("button", { name: /Ouvrir la fiche KB-/ }).first();
  await expect(fiche).toBeVisible();

  const nlu = page.getByLabel("Sorties du modèle NLU").first();
  await expect(nlu.getByText("Catégorie", { exact: true })).toBeVisible();
  await expect(nlu.getByText("Deux intentions les plus probables")).toBeVisible();
  await expect(nlu.getByText("Urgence (0 à 3)")).toBeVisible();
  await page.getByRole("button", { name: "Masquer l'analyse" }).click();
  await expect(page.getByLabel("Sorties du modèle NLU")).toHaveCount(0);
  await page.getByRole("button", { name: "Afficher l'analyse" }).click();
  await expect(page.getByLabel("Sorties du modèle NLU").first()).toBeVisible();

  await answer.getByRole("button", { name: "Utile" }).click();
  await expect(page.getByText("Merci, réponse notée utile.")).toBeVisible();

  await fiche.click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
  expect(problems).toEqual([]);
});

test("chat : trois écritures, script refusé sans exécution, transfert à un conseiller", async ({
  page,
}) => {
  const problems = watch(page);
  await page.goto("/");
  await send(page, "الكونيكسيون مقطوعة من البارح ف الدار");
  await send(page, "Bonjour, ma facture de ce mois est trop élevée");
  const refused = await send(page, "<img src=x onerror=alert(1)> salam");
  await expect(refused.getByText("Message non traité").first()).toBeVisible();

  await page.getByRole("button", { name: "Parler à un conseiller" }).click();
  const transfer = page.getByText(/Transmis à un conseiller · dossier DC-[0-9A-F]{8}/).last();
  await expect(transfer).toBeVisible({ timeout: MODEL_TIMEOUT });
  caseNumber = /DC-[0-9A-F]{8}/.exec((await transfer.textContent()) ?? "")?.[0] ?? "";
  expect(caseNumber).not.toBe("");
  expect(problems).toEqual([]);
});

test("console : le conseiller prend le dossier du client puis le clôture", async ({ page }) => {
  expect(caseNumber, "le test précédent fournit le numéro de dossier").not.toBe("");
  const problems = watch(page);
  await login(page, ADVISOR, ADVISOR_PASSWORD, "Console conseiller");
  await page.getByRole("button", { name: new RegExp(caseNumber) }).click();
  await expect(page.getByRole("heading", { name: `Dossier ${caseNumber}` })).toBeVisible();
  await page.getByRole("button", { name: "Prendre en charge" }).click();
  await page.getByRole("button", { name: "Clôturer le dossier" }).click();
  const detail = page.locator("section[aria-labelledby='titre-dossier']");
  await expect(detail.getByText("Clôturé", { exact: true })).toBeVisible();
  expect(problems).toEqual([]);
});

test("tableau de bord : indicateurs, répartition par écriture, graphiques", async ({ page }) => {
  const problems = watch(page);
  await login(page, ADMIN, ADMIN_PASSWORD, "Tableau de bord");
  for (const label of ["Messages analysés", "F1 macro (test)", "Taux d'escalade", "Latence p95"]) {
    await expect(page.getByText(label, { exact: true })).toBeVisible();
  }
  await expect(page.getByText("Répartition par écriture")).toBeVisible();
  await expect(page.locator(".recharts-bar-rectangle").first()).toBeVisible();
  expect(problems).toEqual([]);
});
