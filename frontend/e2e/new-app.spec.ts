import { test, expect } from '@playwright/test';

const ADMIN_EMAIL = 'admin-e2e@cnp.test';
const ADMIN_PASSWORD = 'AdminE2E123!';

test.describe('New application', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/login');
    await page.getByLabel('Adresse email').fill(ADMIN_EMAIL);
    await page.getByLabel('Mot de passe').fill(ADMIN_PASSWORD);
    await page.getByRole('button', { name: 'Se connecter' }).click();
    await expect(page).toHaveURL(/\/(resources)?$/);
  });

  test('scaffolding an app from a template redirects to the resources list', async ({ page }) => {
    // The scaffold flow normally talks to GitLab — stub the backend calls
    // it depends on so the test only exercises the frontend form/flow.
    await page.route('**/api/v1/apps/templates', async (route) => {
      await route.fulfill({
        json: [{ name: 'Python API', path: 'templates/python-api', web_url: 'https://gitlab.example.com/templates/python-api' }],
      });
    });

    await page.route('**/api/v1/apps/scaffold', async (route) => {
      await route.fulfill({
        json: {
          id: 9999,
          name: 'e2e-app',
          owner: ADMIN_EMAIL,
          status: 'onboarding',
          origin: 'scaffolded',
          repo_url: 'https://gitlab.example.com/cnp-apps/e2e-app',
          created_at: new Date().toISOString(),
        },
      });
    });

    await page.goto('/resources/new');

    await page.getByPlaceholder('mon-service').fill('e2e-app');
    await page.getByRole('combobox').selectOption({ label: 'Python API' });
    await page.getByRole('button', { name: "Créer l'application" }).click();

    await expect(page).toHaveURL(/\/resources$/);
  });
});
