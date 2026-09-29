import { expect, test } from "bun:test";
import fallback, { isUsageLimit, ROUTES } from "../../config/pi/extensions/jev-sonnet-fallback";

test("only provider usage limits trigger a switch", () => {
  expect(isUsageLimit("HTTP 429: usage limit reached")).toBe(true);
  expect(isUsageLimit("401 invalid authentication")).toBe(false);
  expect(isUsageLimit("network timeout")).toBe(false);
});

test("subscription candidates precede metered candidate", () => {
  expect(ROUTES.map(([provider]) => provider)).toEqual(["github-copilot", "cursor", "openrouter"]);
});

test("after a subscription limit, continue on the next authenticated provider", async () => {
  process.env.JEV_ROUTED_SESSION = "1";
  let handler: ((event: any, context: any) => Promise<any>) | undefined;
  let selected = "";
  const pi = {
    on: (_event: string, callback: typeof handler) => { handler = callback; },
    setModel: async (model: { provider: string }) => { selected = model.provider; return true; },
    setThinkingLevel: (level: string) => expect(level).toBe("medium"),
  };
  fallback(pi as any);
  const copilot = { provider: "github-copilot", id: "claude-sonnet-5.5" };
  const cursor = { provider: "cursor", id: "claude-sonnet-5-5" };
  const router = { provider: "openrouter", id: "anthropic/claude-sonnet-5.5" };
  const event = {
    outcome: "error", context: { contextMessages: [{ role: "assistant", stopReason: "error", errorMessage: "usage limit exceeded" }] },
  };
  const ctx = {
    model: copilot, thinkingLevel: "medium", hasUI: false,
    modelRegistry: {
      find: (provider: string) => ({ cursor, openrouter: router } as any)[provider],
      getAvailable: () => [copilot, cursor, router],
    },
  };
  const result = await handler!(event, ctx);
  expect(selected).toBe("cursor");
  expect(result.continue).toBe(true);
  expect(result.entries[0].type).toBe("custom_message");
  ctx.model = cursor;
  await handler!(event, ctx);
  expect(selected).toBe("openrouter");
  delete process.env.JEV_ROUTED_SESSION;
});

test("skip unauthenticated Cursor and stop when the metered provider is exhausted", async () => {
  process.env.JEV_ROUTED_SESSION = "1";
  let handler: ((event: any, context: any) => Promise<any>) | undefined;
  const switched: string[] = [];
  fallback({
    on: (_event: string, callback: typeof handler) => { handler = callback; },
    setModel: async (model: { provider: string }) => { switched.push(model.provider); return true; },
    setThinkingLevel: () => {},
  } as any);
  const copilot = { provider: "github-copilot", id: "claude-sonnet-5.5" };
  const openrouter = { provider: "openrouter", id: "anthropic/claude-sonnet-5.5" };
  const event = { outcome: "error", context: { contextMessages: [{ role: "assistant", stopReason: "error", errorMessage: "429 quota exceeded" }] } };
  const ctx = {
    model: copilot, hasUI: false,
    modelRegistry: { find: (provider: string) => provider === "openrouter" ? openrouter : undefined, getAvailable: () => [copilot, openrouter] },
  };
  expect((await handler!(event, ctx)).continue).toBe(true);
  expect(switched).toEqual(["openrouter"]);
  ctx.model = openrouter;
  expect(await handler!(event, ctx)).toBeUndefined();
  delete process.env.JEV_ROUTED_SESSION;
});
