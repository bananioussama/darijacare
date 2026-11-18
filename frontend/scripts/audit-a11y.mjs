// Audit d'accessibilité automatique (axe-core, règles WCAG 2.0 / 2.1 / 2.2, niveaux A et AA)
// sur le rendu réel des pages. Prérequis : API et interface lancées, comptes conseiller1 et
// admin1 (mot de passe DARIJACARE_CAPTURE_PASSWORD). Usage :
//   DARIJACARE_CAPTURE_PASSWORD=... node scripts/audit-a11y.mjs
// Code de sortie 1 s'il reste une violation.
import AxeBuilder from "@axe-core/playwright";
import { chromium } from "@playwright/test";

const BASE = process.env.DARIJACARE_UI_URL ?? "http://127.0.0.1:5173";
const PASSWORD = process.env.DARIJACARE_CAPTURE_PASSWORD;
if (!PASSWORD) throw new Error("DARIJACARE_CAPTURE_PASSWORD manquant");
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const CONTEXT = {
  viewport: { width: 1366, height: 900 },
  locale: "fr-FR",
  reducedMotion: "reduce",
};

const results = [];
async function audit(page, name) {
  const { violations } = await new AxeBuilder({ page }).withTags(TAGS).analyze();
  results.push({ name, violations });
}

async function login(page, username, heading) {
  await page.goto(`${BASE}/connexion`);
  await page.getByLabel("Identifiant").fill(username);
  await page.getByLabel("Mot de passe").fill(PASSWORD);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await page.getByRole("heading", { name: heading }).waitFor();
}

const browser = await chromium.launch();
try {
  const client = await (await browser.newContext(CONTEXT)).newPage();
  await client.goto(BASE);
  await audit(client, "Assistant (vide)");
  await client.getByRole("button", { name: /chargit 20dh/ }).click();
  await client.locator("article[aria-busy='false']").first().waitFor({ timeout: 90_000 });
  await audit(client, "Assistant (réponse, panneau d'analyse)");
  await client.getByRole("button", { name: "Corriger" }).first().click();
  await client.getByLabel("Quelle était la bonne intention ?").waitFor();
  await audit(client, "Assistant (correction)");
  await client
    .getByRole("button", { name: /Ouvrir la fiche/ })
    .first()
    .click();
  await client.getByRole("dialog").waitFor();
  await audit(client, "Fiche (fenêtre)");
  await client.keyboard.press("Escape");
  await client.goto(`${BASE}/historique`);
  await client.getByLabel("Réponse de l'assistant").first().waitFor();
  await audit(client, "Historique de session");
  await client.goto(BASE);
  await client.getByRole("button", { name: "Parler à un conseiller" }).click();
  await client.getByText(/Transmis à un conseiller · dossier/).waitFor({ timeout: 90_000 });
  await audit(client, "Assistant (escalade vers un conseiller)");
  await client.goto(`${BASE}/credits`);
  await audit(client, "Crédits");
  await client.goto(`${BASE}/page-inexistante`);
  await audit(client, "Page introuvable");
  await client.goto(`${BASE}/connexion`);
  await audit(client, "Connexion");

  const mobile = await (
    await browser.newContext({ ...CONTEXT, viewport: { width: 390, height: 844 }, isMobile: true })
  ).newPage();
  await mobile.goto(BASE);
  await mobile.getByRole("button", { name: "Menu" }).click();
  await audit(mobile, "Mobile (menu ouvert)");

  const advisor = await (await browser.newContext(CONTEXT)).newPage();
  await login(advisor, "conseiller1", "Console conseiller");
  await advisor.getByRole("button", { name: /DC-/ }).first().click();
  await advisor.getByRole("heading", { name: /Dossier DC-/ }).waitFor();
  await audit(advisor, "Console conseiller (dossier ouvert)");

  const admin = await (await browser.newContext(CONTEXT)).newPage();
  await login(admin, "admin1", "Tableau de bord");
  await admin.locator(".recharts-bar-rectangle").first().waitFor();
  await audit(admin, "Tableau de bord");
  await admin.goto(`${BASE}/administration`);
  await admin.getByText(/Fiches \(75\)/).waitFor();
  await audit(admin, "Base et modèles");
} finally {
  await browser.close();
}

let total = 0;
for (const { name, violations } of results) {
  total += violations.length;
  console.log(`${violations.length === 0 ? "OK " : "KO "} ${name}`);
  for (const v of violations) {
    console.log(`     [${v.impact}] ${v.id} : ${v.help} (${v.nodes.length} élément(s))`);
    for (const node of v.nodes.slice(0, 3)) console.log(`        ${node.target.join(" ")}`);
  }
}
console.log(`${results.length} pages auditées, ${total} violation(s).`);
process.exitCode = total === 0 ? 0 : 1;
