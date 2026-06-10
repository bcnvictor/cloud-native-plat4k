import { test, expect } from '@playwright/test';

const ADMIN_EMAIL = 'admin-e2e@cnp.test';
const ADMIN_PASSWORD = 'AdminE2E123!';

test.describe('Login / logout', () => {
  test('login redirects to the app and logout returns to /login', async ({ page }) => {
    await page.goto('/login');

    await page.getByLabel('Adresse email').fill(ADMIN_EMAIL);
    await page.getByLabel('Mot de passe').fill(ADMIN_PASSWORD);
    await page.getByRole('button', { name: 'Se connecter' }).click();

    await expect(page).toHaveURL(/\/(resources)?$/);
    await expect(page.locator('.sb-user-email')).toHaveText(ADMIN_EMAIL);

    await page.locator('.sb-logout').click();

    await expect(page).toHaveURL(/\/login$/);
  });

  test('wrong password shows an error and stays on /login', async ({ page }) => {
    await page.goto('/login');

    await page.getByLabel('Adresse email').fill(ADMIN_EMAIL);
    await page.getByLabel('Mot de passe').fill('wrong-password');
    await page.getByRole('button', { name: 'Se connecter' }).click();

    await expect(page.locator('.login-error')).toBeVisible();
    await expect(page).toHaveURL(/\/login$/);
  });
});
