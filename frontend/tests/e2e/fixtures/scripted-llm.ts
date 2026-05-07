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

const BACKEND =
  process.env.WENJIN_BACKEND_URL ?? "http://localhost:8000";

interface AgentMessageJSON {
  blocks: Array<Record<string, unknown>>;
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
