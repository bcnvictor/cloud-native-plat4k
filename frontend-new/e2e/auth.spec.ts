import { test, expect } from '@playwright/test';

const ADMIN = { email: 'admin-e2e@cnp.test', password: 'AdminE2E123!' };
const DEV   = { email: 'dev-e2e@cnp.test',   password: 'DevE2E123!' };

test.describe('Login', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
  });

  test('affiche le formulaire de login', async ({ page }) => {
    await expect(page.getByRole('heading', { name: /cloud native platform/i })).toBeVisible();
    await expect(page.getByLabel(/email/i)).toBeVisible();
    await expect(page.getByLabel(/password/i)).toBeVisible();
  });

  test('admin sans groupe → redirigé vers /admin/clusters', async ({ page }) => {
    await page.getByLabel(/email/i).fill(ADMIN.email);
    await page.getByLabel(/password/i).fill(ADMIN.password);
    await page.getByRole('button', { name: /connexion|login|se connecter|sign in/i }).click();

    await expect(page).toHaveURL(/\/admin\/clusters/, { timeout: 10_000 });
  });

  test('mauvais mot de passe → message d\'erreur', async ({ page }) => {
    await page.getByLabel(/email/i).fill(ADMIN.email);
    await page.getByLabel(/password/i).fill('wrong-password');
    await page.getByRole('button', { name: /connexion|login|se connecter|sign in/i }).click();

    await expect(page.locator('p.text-danger-text')).toBeVisible({ timeout: 5_000 });
    await expect(page).toHaveURL(/\/login/);
  });

  test('utilisateur dev sans groupe → reste sur /login', async ({ page }) => {
    await page.getByLabel(/email/i).fill(DEV.email);
    await page.getByLabel(/password/i).fill(DEV.password);
    await page.getByRole('button', { name: /connexion|login|se connecter|sign in/i }).click();

    // DEV sans groupe → RootRedirect renvoie sur /login
    await expect(page).toHaveURL(/\/login/, { timeout: 10_000 });
  });
});

test.describe('Accès non authentifié', () => {
  test('route protégée → redirigé vers /login', async ({ page }) => {
    await page.goto('/admin/clusters');
    await expect(page).toHaveURL(/\/login/, { timeout: 5_000 });
  });

  test('route admin → redirigé vers /login sans token', async ({ page }) => {
    await page.goto('/admin/users');
    await expect(page).toHaveURL(/\/login/, { timeout: 5_000 });
  });
});
