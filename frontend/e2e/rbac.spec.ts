import { test, expect } from '@playwright/test';

const DEV_EMAIL = 'dev-e2e@cnp.test';
const DEV_PASSWORD = 'DevE2E123!';

test.describe('Role-based access control', () => {
  test('a dev user is redirected away from /admin/users', async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel('Adresse email').fill(DEV_EMAIL);
    await page.getByLabel('Mot de passe').fill(DEV_PASSWORD);
    await page.getByRole('button', { name: 'Se connecter' }).click();

    await expect(page).toHaveURL(/\/(resources)?$/);

    // The "Utilisateurs" admin link must not even be rendered for a dev.
    await expect(page.getByRole('button', { name: 'Utilisateurs' })).toHaveCount(0);

    // Direct navigation must redirect away from the admin page.
    await page.goto('/admin/users');
    await expect(page).toHaveURL(/\/dashboard$/);
  });
});
