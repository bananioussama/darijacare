// Prépare le compte conseiller des tests E2E (une seule fois) avec le compte administrateur.
import { request, type FullConfig } from "@playwright/test";

export const ADVISOR = "e2e.conseiller";

export default async function globalSetup(config: FullConfig): Promise<void> {
  const admin = process.env.DARIJACARE_ADMIN_USERNAME;
  const adminPassword = process.env.DARIJACARE_ADMIN_PASSWORD;
  const advisorPassword = process.env.DARIJACARE_E2E_PASSWORD;
  if (!admin || !adminPassword || !advisorPassword) {
    throw new Error(
      "DARIJACARE_ADMIN_USERNAME, DARIJACARE_ADMIN_PASSWORD et DARIJACARE_E2E_PASSWORD requis (.env)",
    );
  }
  const baseURL = String(config.projects[0].use.baseURL);
  const api = await request.newContext({ baseURL, ignoreHTTPSErrors: true });
  try {
    const login = await api.post("/api/auth/login", {
      data: { username: admin, password: adminPassword },
    });
    if (!login.ok()) throw new Error(`Connexion administrateur impossible (${login.status()})`);
    const { access_token: token } = (await login.json()) as { access_token: string };
    const created = await api.post("/api/admin/users", {
      headers: { Authorization: `Bearer ${token}` },
      data: { username: ADVISOR, password: advisorPassword, role: "conseiller" },
    });
    // 409 : le compte existe déjà (lancements précédents).
    if (!created.ok() && created.status() !== 409) {
      throw new Error(`Création du compte conseiller impossible (${created.status()})`);
    }
  } finally {
    await api.dispose();
  }
}
