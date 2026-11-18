// Captures d'écran de l'interface avec les vrais modèles (vérification visuelle, rapport).
// Prérequis : API lancée (make api) et interface lancée (npm run dev), comptes conseiller1
// et admin1 ayant le mot de passe DARIJACARE_CAPTURE_PASSWORD. Usage :
//   DARIJACARE_CAPTURE_PASSWORD=... node scripts/captures.mjs [dossier de sortie]
// « Mouvement réduit » est émulé : les graphiques sont dessinés sans animation.
import { mkdirSync } from "node:fs";
import path from "node:path";

import { chromium } from "@playwright/test";

const BASE = process.env.DARIJACARE_UI_URL ?? "http://127.0.0.1:5173";
const PASSWORD = process.env.DARIJACARE_CAPTURE_PASSWORD;
const OUT = path.resolve(process.argv[2] ?? "../reports/demo/phase5");
if (!PASSWORD) throw new Error("DARIJACARE_CAPTURE_PASSWORD manquant");
mkdirSync(OUT, { recursive: true });

const DESKTOP = {
  viewport: { width: 1366, height: 900 },
  locale: "fr-FR",
  reducedMotion: "reduce",
};
const answers = (page) => page.locator("article[aria-busy='false']");
const shot = (page, name, fullPage = false) =>
  page.screenshot({ path: path.join(OUT, `${name}.png`), fullPage });

async function send(page, text) {
  const before = await answers(page).count();
  await page.getByLabel("Votre message").fill(text);
  await page.getByLabel("Votre message").press("Enter");
  await answers(page).nth(before).waitFor({ timeout: 90_000 });
}

async function login(page, username, heading) {
  await page.goto(`${BASE}/connexion`);
  await page.getByLabel("Identifiant").fill(username);
  await page.getByLabel("Mot de passe").fill(PASSWORD);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await page.getByRole("heading", { name: heading }).waitFor();
}

const browser = await chromium.launch();
const problems = [];
const watch = (page) => {
  page.on("pageerror", (e) => problems.push(e.message));
  page.on("console", (m) => m.type() === "error" && problems.push(m.text()));
};
try {
  const client = await (await browser.newContext(DESKTOP)).newPage();
  watch(client);
  await client.goto(BASE);
  await shot(client, "01-accueil");
  await client.getByRole("button", { name: /الكونيكسيون مقطوعة/ }).click();
  await answers(client).first().waitFor({ timeout: 90_000 });
  await send(client, "chargit 20dh w ma wslatni walo, 3afak chofo lia");
  await send(client, "Bonjour, ma facture de ce mois est trop élevée, je veux comprendre");
  await shot(client, "02-chat-trois-ecritures");
  await client.getByRole("button", { name: "Parler à un conseiller" }).click();
  await client.getByText(/Transmis à un conseiller · dossier/).waitFor({ timeout: 90_000 });
  await shot(client, "03-chat-conseiller");
  await client.getByRole("button", { name: /Ouvrir la fiche KB-home_outage/ }).click();
  await client.getByRole("dialog").waitFor();
  await shot(client, "04-fiche");

  const phone = await (
    await browser.newContext({
      ...DESKTOP,
      viewport: { width: 390, height: 844 },
      isMobile: true,
      hasTouch: true,
    })
  ).newPage();
  watch(phone);
  await phone.goto(BASE);
  await phone.getByRole("button", { name: /solde dyali sala/ }).click();
  await answers(phone).first().waitFor({ timeout: 90_000 });
  await shot(phone, "05-mobile");

  const advisor = await (await browser.newContext(DESKTOP)).newPage();
  watch(advisor);
  await login(advisor, "conseiller1", "Console conseiller");
  // Premier dossier encore « Nouveau » (la base peut contenir des dossiers déjà pris).
  await advisor.getByRole("button", { name: /DC-/ }).filter({ hasText: "Nouveau" }).first().click();
  await advisor.getByRole("button", { name: "Prendre en charge" }).click();
  await advisor.getByRole("button", { name: "Clôturer le dossier" }).waitFor();
  await shot(advisor, "06-console", true);

  const admin = await (
    await browser.newContext({ ...DESKTOP, viewport: { width: 1366, height: 1100 } })
  ).newPage();
  watch(admin);
  await login(admin, "admin1", "Tableau de bord");
  await admin.locator(".recharts-bar-rectangle").first().waitFor();
  await shot(admin, "07-tableau-de-bord");
  await admin.goto(`${BASE}/administration`);
  await admin.getByText(/Fiches \(75\)/).waitFor();
  await shot(admin, "08-administration");
} finally {
  await browser.close();
}
console.log(`Captures dans ${OUT}`);
if (problems.length) {
  console.error(`Erreurs du navigateur :\n${problems.join("\n")}`);
  process.exitCode = 1;
}
