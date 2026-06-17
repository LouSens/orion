/**
 * E2E tests — Login / Role selection flow (HeroPage).
 *
 * Covers:
 *  - Page loads with the three role buttons
 *  - Each role navigates to the correct form
 *  - Empty form shows validation errors
 *  - Valid employee form navigates to /employee
 *  - Back button returns to role list
 */
import { expect, test } from '@playwright/test';

test.describe('HeroPage — landing and role selection', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // Scroll to the sign-in section (it lives below the hero)
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForSelector('text=Sign in as Employee', { timeout: 5000 });
  });

  test('shows three role buttons', async ({ page }) => {
    await expect(page.getByText('Sign in as Employee')).toBeVisible();
    await expect(page.getByText('Sign in as Manager')).toBeVisible();
    await expect(page.getByText('Sign in as Finance')).toBeVisible();
  });

  test('employee role reveals employee-specific fields', async ({ page }) => {
    await page.getByText('Sign in as Employee').click();
    await expect(page.getByText(/Employee Sign In/i)).toBeVisible();
    await expect(page.getByText('Employee ID')).toBeVisible();
    await expect(page.getByText('Department')).toBeVisible();
  });

  test('manager role reveals manager-specific fields', async ({ page }) => {
    await page.getByText('Sign in as Manager').click();
    await expect(page.getByText(/Manager Sign In/i)).toBeVisible();
    await expect(page.getByText('Manager ID')).toBeVisible();
    await expect(page.getByText('Team / Division')).toBeVisible();
  });

  test('finance role reveals authorization code field', async ({ page }) => {
    await page.getByText('Sign in as Finance').click();
    await expect(page.getByText(/Finance Sign In/i)).toBeVisible();
    await expect(page.getByText('Authorization / Access Code')).toBeVisible();
  });

  test('back button returns to role list', async ({ page }) => {
    await page.getByText('Sign in as Employee').click();
    await page.getByText('← Back to roles').click();
    await expect(page.getByText('Sign in as Employee')).toBeVisible();
  });
});

test.describe('HeroPage — form validation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForSelector('text=Sign in as Employee');
  });

  test('employee form shows validation errors on empty submit', async ({ page }) => {
    await page.getByText('Sign in as Employee').click();
    await page.getByText('Continue to Dashboard').click();
    const errors = page.locator('text=This field is required.');
    await expect(errors.first()).toBeVisible();
  });

  test('manager form shows validation errors on empty submit', async ({ page }) => {
    await page.getByText('Sign in as Manager').click();
    await page.getByText('Continue to Dashboard').click();
    const errors = page.locator('text=This field is required.');
    await expect(errors.first()).toBeVisible();
  });

  test('finance form shows validation errors on empty submit', async ({ page }) => {
    await page.getByText('Sign in as Finance').click();
    await page.getByText('Continue to Dashboard').click();
    const errors = page.locator('text=This field is required.');
    await expect(errors.first()).toBeVisible();
  });
});

test.describe('HeroPage — successful login navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForSelector('text=Sign in as Employee');
  });

  test('valid employee login navigates to /employee', async ({ page }) => {
    await page.getByText('Sign in as Employee').click();

    const inputs = page.locator('input');
    await inputs.nth(0).fill('Alice Tan');          // Full Name
    await inputs.nth(1).fill('E001');               // Employee ID
    await inputs.nth(2).fill('alice@example.com');  // Contact

    await page.locator('select').selectOption('Engineering');
    await page.getByText('Continue to Dashboard').click();

    await expect(page).toHaveURL('/employee', { timeout: 5000 });
  });

  test('valid manager login navigates to /manager', async ({ page }) => {
    await page.getByText('Sign in as Manager').click();

    const inputs = page.locator('input');
    await inputs.nth(0).fill('Bob Manager');         // Full Name
    await inputs.nth(1).fill('M002');                // Manager ID
    await inputs.nth(2).fill('Product');             // Team
    await inputs.nth(3).fill('bob@example.com');     // Email

    await page.getByText('Continue to Dashboard').click();
    await expect(page).toHaveURL('/manager', { timeout: 5000 });
  });

  test('valid finance login navigates to /finance', async ({ page }) => {
    await page.getByText('Sign in as Finance').click();

    const inputs = page.locator('input');
    await inputs.nth(0).fill('Carol Finance');       // Full Name
    await inputs.nth(1).fill('F003');                // Employee ID
    await inputs.nth(2).fill('carol@example.com');   // Contact

    await page.locator('select').selectOption('Finance');

    // Find the password field and fill it
    await page.locator('input[type="password"]').fill('FINANCE-SECRET-001');
    await page.getByText('Continue to Dashboard').click();
    await expect(page).toHaveURL('/finance', { timeout: 5000 });
  });
});

test.describe('HeroPage — auth code toggle', () => {
  test('auth code show/hide toggle works', async ({ page }) => {
    await page.goto('/');
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
    await page.waitForSelector('text=Sign in as Finance');

    await page.getByText('Sign in as Finance').click();

    const pwInput = page.locator('input[type="password"]');
    await expect(pwInput).toBeVisible();

    // Click the toggle button (eye icon)
    await page.locator('button[type="button"]').click();

    const textInput = page.locator('input[type="text"]').last();
    await expect(textInput).toBeVisible();
  });
});
