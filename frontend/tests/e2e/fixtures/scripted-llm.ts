/**
 * Scripted-LLM helpers for Playwright e2e (Plan 3 T2).
 *
 * Backend exposes /__test__/llm/queue and /__test__/llm/clear when the
 * environment is not "production". Tests queue scripted AgentMessage
 * payloads BEFORE navigating to the chat page; parse_with_fallback then
 * pops them in order instead of calling the real LLM.
 *
 * Workspace minting goes through /__test__/workspaces, which creates a
 * fresh workspace bound to the synthetic e2e user.
 */

import type { BrowserContext, Page } from "@playwright/test";

const BACKEND =
  process.env.WENJIN_BACKEND_URL ?? "http://localhost:8001";
const AUTH_STORAGE_KEY = "auth-storage";
const E2E_USER_EMAIL = "e2e-test@example.com";
const E2E_USER_PASSWORD = "wenjin-e2e-password";
const AUTH_COOKIE = JSON.stringify({
  state: { isAuthenticated: true },
});

interface AgentMessageJSON {
  blocks: Array<Record<string, unknown>>;
}

interface TokenPayload {
  access_token: string;
  refresh_token: string;
}

interface AuthUserPayload {
  id: string;
  email: string;
  name: string | null;
  role: string;
  credits?: number;
  total_credits_earned?: number;
  total_credits_spent?: number;
}

async function loginE2EUser(): Promise<{
  accessToken: string;
  refreshToken: string;
  user: AuthUserPayload;
}> {
  const loginResponse = await fetch(`${BACKEND}/api/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      email: E2E_USER_EMAIL,
      password: E2E_USER_PASSWORD,
    }),
  });
  if (!loginResponse.ok) {
    throw new Error(
      `loginE2EUser failed: ${loginResponse.status} ${await loginResponse.text()}`,
    );
  }

  const tokens = (await loginResponse.json()) as TokenPayload;
  const meResponse = await fetch(`${BACKEND}/api/auth/me`, {
    headers: {
      Authorization: `Bearer ${tokens.access_token}`,
    },
  });
  if (!meResponse.ok) {
    throw new Error(
      `loginE2EUser(/me) failed: ${meResponse.status} ${await meResponse.text()}`,
    );
  }

  const user = (await meResponse.json()) as AuthUserPayload;
  return {
    accessToken: tokens.access_token,
    refreshToken: tokens.refresh_token,
    user,
  };
}

export async function queueLLM(messages: AgentMessageJSON[]): Promise<void> {
  const r = await fetch(`${BACKEND}/__test__/llm/queue`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ messages }),
  });
  if (!r.ok) {
    throw new Error(`queueLLM failed: ${r.status} ${await r.text()}`);
  }
}

export async function clearLLM(): Promise<void> {
  await fetch(`${BACKEND}/__test__/llm/clear`, { method: "POST" });
}

export async function setupCleanWorkspace(): Promise<{
  workspaceId: string;
}> {
  const r = await fetch(`${BACKEND}/__test__/workspaces`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ type: "sci", name: "E2E Workspace" }),
  });
  if (!r.ok) {
    throw new Error(`setupCleanWorkspace failed: ${r.status} ${await r.text()}`);
  }
  const data = (await r.json()) as { workspace_id: string };
  return { workspaceId: data.workspace_id };
}

export async function seedAuthenticatedSession(
  page: Page,
  context: BrowserContext,
): Promise<void> {
  const session = await loginE2EUser();
  await context.addCookies([
    {
      name: AUTH_STORAGE_KEY,
      value: encodeURIComponent(AUTH_COOKIE),
      domain: "localhost",
      path: "/",
    },
  ]);
  await page.addInitScript(
    ({ storageKey, storageValue }) => {
      window.localStorage.setItem(storageKey, storageValue);
    },
    {
      storageKey: AUTH_STORAGE_KEY,
      storageValue: JSON.stringify({
        state: {
          user: session.user,
          accessToken: session.accessToken,
          refreshToken: session.refreshToken,
          isAuthenticated: true,
          isLoading: false,
          error: null,
        },
        version: 0,
      }),
    },
  );
}
