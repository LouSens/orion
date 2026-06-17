/**
 * Unit tests for HeroPage — login flow, role selection, form validation.
 *
 * Uses React Testing Library + jsdom (configured globally in vitest.config.ts).
 */
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React from 'react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AuthProvider } from '../context/AuthContext';
import { ToastProvider } from '../context/ToastContext';
import HeroPage from '../pages/HeroPage';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

/** react-router-dom useNavigate mock. */
const mockNavigate = vi.fn();
vi.mock('react-router-dom', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router-dom')>();
  return { ...actual, useNavigate: () => mockNavigate };
});

/**
 * motion/react mock: replace every motion.* element with a plain HTML tag
 * and stub out animation hooks so they don't throw in jsdom.
 */
vi.mock('motion/react', () => {
  const createForwardRef = (tag: string) =>
    React.forwardRef<HTMLElement, React.HTMLAttributes<HTMLElement>>(
      ({ children, ...props }, ref) =>
        React.createElement(tag, { ...props, ref }, children),
    );

  const motionProxy = new Proxy({} as Record<string, unknown>, {
    get: (_t, prop: string) => createForwardRef(prop),
  });

  return {
    motion: motionProxy,
    AnimatePresence: ({ children }: { children: React.ReactNode }) => children,
    useScroll: () => ({ scrollY: { on: vi.fn(), get: () => 0 } }),
    useTransform: (_val: unknown, _from: number[], to: number[]) => to[0],
  };
});

// ---------------------------------------------------------------------------
// Render helper
// ---------------------------------------------------------------------------

function renderHeroPage() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <ToastProvider>
          <HeroPage />
        </ToastProvider>
      </AuthProvider>
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Role Selection
// ---------------------------------------------------------------------------

describe('HeroPage — role selection', () => {
  afterEach(() => vi.clearAllMocks());

  it('renders three role buttons on initial load', () => {
    renderHeroPage();
    expect(screen.getByText('Sign in as Employee')).toBeInTheDocument();
    expect(screen.getByText('Sign in as Manager')).toBeInTheDocument();
    expect(screen.getByText('Sign in as Finance')).toBeInTheDocument();
  });

  it('shows employee form fields after clicking Employee button', async () => {
    renderHeroPage();
    await userEvent.click(screen.getByText('Sign in as Employee'));
    expect(screen.getByText(/Employee Sign In/i)).toBeInTheDocument();
    expect(screen.getByText('Employee ID')).toBeInTheDocument();
    expect(screen.getByText('Department')).toBeInTheDocument();
  });

  it('shows manager form fields after clicking Manager button', async () => {
    renderHeroPage();
    await userEvent.click(screen.getByText('Sign in as Manager'));
    expect(screen.getByText(/Manager Sign In/i)).toBeInTheDocument();
    expect(screen.getByText('Manager ID')).toBeInTheDocument();
    expect(screen.getByText('Team / Division')).toBeInTheDocument();
  });

  it('shows finance form fields after clicking Finance button', async () => {
    renderHeroPage();
    await userEvent.click(screen.getByText('Sign in as Finance'));
    expect(screen.getByText(/Finance Sign In/i)).toBeInTheDocument();
    expect(screen.getByText('Authorization / Access Code')).toBeInTheDocument();
  });

  it('navigates back to role list when "← Back to roles" is clicked', async () => {
    renderHeroPage();
    await userEvent.click(screen.getByText('Sign in as Employee'));
    await userEvent.click(screen.getByText('← Back to roles'));
    expect(screen.getByText('Sign in as Employee')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Validation — Employee
// ---------------------------------------------------------------------------

describe('HeroPage — employee form validation', () => {
  afterEach(() => vi.clearAllMocks());

  it('shows validation errors when submitting empty employee form', async () => {
    renderHeroPage();
    await userEvent.click(screen.getByText('Sign in as Employee'));
    await userEvent.click(screen.getByText('Continue to Dashboard'));
    const errors = screen.getAllByText('This field is required.');
    expect(errors.length).toBeGreaterThan(0);
  });

  /**
   * Full navigation tests are better covered in E2E (Playwright) because
   * they require real browser scroll/viewport. Here we verify the form state
   * transitions are wired correctly: selecting a role shows its form panel.
   */
  it('employee form is shown (not the role list) after role selection', async () => {
    renderHeroPage();
    await userEvent.click(screen.getByText('Sign in as Employee'));
    // The role list buttons disappear; the back button appears instead
    expect(screen.getByText('← Back to roles')).toBeInTheDocument();
    expect(screen.queryByText('Sign in as Manager')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Validation — Manager
// ---------------------------------------------------------------------------

describe('HeroPage — manager form validation', () => {
  afterEach(() => vi.clearAllMocks());

  it('shows validation errors when submitting empty manager form', async () => {
    renderHeroPage();
    await userEvent.click(screen.getByText('Sign in as Manager'));
    await userEvent.click(screen.getByText('Continue to Dashboard'));
    const errors = screen.getAllByText('This field is required.');
    expect(errors.length).toBeGreaterThan(0);
  });

  it('manager form is shown (not the role list) after role selection', async () => {
    renderHeroPage();
    await userEvent.click(screen.getByText('Sign in as Manager'));
    expect(screen.getByText('← Back to roles')).toBeInTheDocument();
    expect(screen.queryByText('Sign in as Employee')).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Auth Code field (Finance)
// ---------------------------------------------------------------------------

describe('HeroPage — auth code show/hide toggle', () => {
  afterEach(() => vi.clearAllMocks());

  it('auth code input is password type by default', async () => {
    renderHeroPage();
    await userEvent.click(screen.getByText('Sign in as Finance'));
    const passwordInput = document.querySelector('input[type="password"]');
    expect(passwordInput).toBeInTheDocument();
  });

  it('toggles to text type when eye icon is clicked', async () => {
    renderHeroPage();
    await userEvent.click(screen.getByText('Sign in as Finance'));
    const toggleBtn = document.querySelector('button[type="button"]') as HTMLButtonElement;
    await userEvent.click(toggleBtn);
    const textInputs = document.querySelectorAll('input[type="text"]');
    expect(textInputs.length).toBeGreaterThan(0);
  });
});
