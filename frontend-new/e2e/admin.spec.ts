import { test, expect, Page } from '@playwright/test';

const ADMIN = { email: 'admin-e2e@cnp.test', password: 'AdminE2E123!' };
const DEV   = { email: 'dev-e2e@cnp.test',   password: 'DevE2E123!' };

async function loginAs(page: Page, user: { email: string; password: string }) {
  await page.goto('/login');
  await page.getByLabel(/email/i).fill(user.email);
  await page.getByLabel(/mot de passe|password/i).fill(user.password);
  await page.getByRole('button', { name: /connexion|login|se connecter/i }).click();
  await page.waitForURL(url => !url.pathname.includes('/login'), { timeout: 10_000 });
}

test.describe('RBAC admin', () => {
  test('admin accède à /admin/clusters', async ({ page }) => {
    await loginAs(page, ADMIN);
    await page.goto('/admin/clusters');
    await expect(page).toHaveURL(/\/admin\/clusters/);
    // La page charge sans erreur 403/redirect
    await expect(page.locator('body')).not.toContainText('403');
  });

  test('admin accède à /admin/users', async ({ page }) => {
    await loginAs(page, ADMIN);
    await page.goto('/admin/users');
    await expect(page).toHaveURL(/\/admin\/users/);
  });

  test('utilisateur dev ne peut pas accéder à /admin/clusters', async ({ page }) => {
    await loginAs(page, DEV);
    // DEV n'a pas de groupe, loginAs le redirige vers /login
    // On vérifie qu'en allant directement sur /admin, il est refusé
    await page.goto('/admin/clusters');
    await expect(page).not.toHaveURL(/\/admin\/clusters/, { timeout: 5_000 });
  });
});

test.describe('Navigation admin', () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, ADMIN);
    await page.goto('/admin/clusters');
  });

  test('sidebar visible avec liens admin', async ({ page }) => {
    const sidebar = page.locator('aside, nav, [class*=sidebar]').first();
    await expect(sidebar).toBeVisible();
  });

  test('naviguer vers /admin/users depuis /admin/clusters', async ({ page }) => {
    // Clic sur le lien Utilisateurs dans la sidebar
    await page.locator('a[href*="/admin/users"], button:has-text("Utilisateurs")').first().click();
    await expect(page).toHaveURL(/\/admin\/users/, { timeout: 5_000 });
  });

  test('logout fonctionne', async ({ page }) => {
    // Bouton logout dans la sidebar
    await page.locator('button[title*="onnexion"], button[title*="ogout"]').first().click();
    await expect(page).toHaveURL(/\/login/, { timeout: 5_000 });
    // Vérifier que le token a été effacé
    const token = await page.evaluate(() => localStorage.getItem('token'));
    expect(token).toBeNull();
  });
});
