import { expect, test } from "bun:test";
import cases from "./jev_effort_cases.json";
import fallback, { buildRequestBody, redirectCodexAgent, chooseEffort, effortFromAnswers, fallbackCandidates, hitUsageLimit, isUsageLimit, ROUTES, workerBaseModel } from "../../config/pi/extensions/jev-sonnet-fallback";

test("only provider usage limits trigger a switch", () => {
  expect(isUsageLimit("HTTP 429: usage limit reached")).toBe(true);
  expect(isUsageLimit("401 invalid authentication")).toBe(false);
  expect(isUsageLimit("network timeout")).toBe(false);
});

test("only explicit status or machine error kinds count as provider limits", () => {
  for (const message of ["429 quota exceeded", "HTTP/2 429", "statusCode=429", "Error: status code 429", '{"status":429}', '{"error":{"type":"rate_limit_error"}}', '{"error":{"code":"insufficient_quota"}}', "RESOURCE_EXHAUSTED", "rate_limit_error: provider stopped"]) {
    expect(isUsageLimit(message)).toBe(true);
  }
  for (const message of ["Request ID 429 failed: authentication error (401)", "Rate limiter configuration is invalid (400)", "quota exceeded", "rate limit reached", "no usage limit exceeded", "not RESOURCE_EXHAUSTED", "4290 quota exceeded", "HTTP 429.1", "HTTP 429/401", "statusCode=4291", 'HTTP 400: fixture says "HTTP 429: usage limit reached"', '401 fixture says "quota exceeded"', '403 fixture says "rate limit reached"', 'HTTP 500: fixture says "429"', "HTTP 429, statusCode=401", "rate_limit_error: HTTP 401", '{"status":401,"error":{"type":"rate_limit_error"}}', '{"status":429,"error":{"status":401}}', '{"error":{"type":"authentication_error","message":"HTTP 429"}}', '{"status":true,"error":{"type":"rate_limit_error"}}']) {
    expect(isUsageLimit(message)).toBe(false);
  }
});

test("an ambiguous error neither switches nor exhausts a route", async () => {
  process.env.JEV_ROUTED_SESSION = "1";
  let handler: ((event: any, context: any) => Promise<any>) | undefined;
  const switched: string[] = [];
  const thinking: string[] = [];
  const copilot = { provider: "github-copilot", id: "claude-sonnet-5.5" };
  const router = { provider: "openrouter", id: "anthropic/claude-sonnet-5.5" };
  fallback({
    on: (name: string, cb: typeof handler) => { if (name === "agent_before_settle") handler = cb; },
    setModel: async (model: any) => { switched.push(model.provider); return true; },
    setThinkingLevel: (level: string) => thinking.push(level),
  } as any);
  const ctx = { model: copilot, hasUI: false, thinkingLevel: "high", modelRegistry: {
    getAvailable: () => [copilot, router],
    find: (provider: string) => provider === "github-copilot" ? copilot : router,
  } };
  const event = (errorMessage: string) => ({ outcome: "error", context: { contextMessages: [{ role: "assistant", stopReason: "error", errorMessage }] } });
  for (const message of ["Request ID 429 failed: authentication error (401)", "Rate limiter configuration is invalid (400)", "quota exceeded", "HTTP 429, statusCode=401"]) {
    expect(await handler!(event(message), ctx)).toBeUndefined();
  }
  expect(switched).toEqual([]);
  expect(thinking).toEqual([]);
  // Copilot must still be eligible: only the genuine Router limit exhausts a route.
  ctx.model = router;
  const result = await handler!(event("HTTP 429: provider quota exceeded"), ctx);
  expect(switched).toEqual(["github-copilot"]);
  expect(thinking).toEqual(["high"]);
  expect(result.continue).toBe(true);
  delete process.env.JEV_ROUTED_SESSION;
});

test("subscription candidates precede metered candidate", () => {
  expect(ROUTES.map(([provider]) => provider)).toEqual(["github-copilot", "anthropic", "openrouter"]);
});

test("after a subscription limit, continue on the next authenticated provider", async () => {
  process.env.JEV_ROUTED_SESSION = "1";
  let handler: ((event: any, context: any) => Promise<any>) | undefined;
  let selected = "";
  const pi = {
    on: (name: string, callback: typeof handler) => { if (name === "agent_before_settle") handler = callback; },
    setModel: async (model: { provider: string }) => { selected = model.provider; return true; },
    setThinkingLevel: (level: string) => expect(level).toBe("medium"),
  };
  fallback(pi as any);
  const copilot = { provider: "github-copilot", id: "claude-sonnet-5.5" };
  const anthropic = { provider: "anthropic", id: "claude-sonnet-5-5" };
  const router = { provider: "openrouter", id: "anthropic/claude-sonnet-5.5" };
  const event = {
    outcome: "error", context: { contextMessages: [{ role: "assistant", stopReason: "error", errorMessage: "HTTP 429: usage limit exceeded" }] },
  };
  const ctx = {
    model: copilot, thinkingLevel: "medium", hasUI: false,
    modelRegistry: {
      find: (provider: string) => ({ anthropic, openrouter: router } as any)[provider],
      getAvailable: () => [copilot, anthropic, router],
    },
  };
  const result = await handler!(event, ctx);
  expect(selected).toBe("anthropic");
  expect(result.continue).toBe(true);
  expect(result.entries[0].type).toBe("custom_message");
  ctx.model = anthropic;
  await handler!(event, ctx);
  expect(selected).toBe("openrouter");
  delete process.env.JEV_ROUTED_SESSION;
});

test("Cursor is never a fallback, even when authenticated: Pi gives that provider no tools", async () => {
  process.env.JEV_ROUTED_SESSION = "1";
  let handler: ((event: any, context: any) => Promise<any>) | undefined;
  const switched: string[] = [];
  fallback({
    on: (name: string, callback: typeof handler) => { if (name === "agent_before_settle") handler = callback; },
    setModel: async (model: { provider: string }) => { switched.push(model.provider); return true; },
    setThinkingLevel: () => {},
  } as any);
  const copilot = { provider: "github-copilot", id: "claude-sonnet-5.5" };
  const cursor = { provider: "cursor", id: "claude-sonnet-5-5" };
  const openrouter = { provider: "openrouter", id: "anthropic/claude-sonnet-5.5" };
  const event = { outcome: "error", context: { contextMessages: [{ role: "assistant", stopReason: "error", errorMessage: "429 quota exceeded" }] } };
  const ctx = {
    model: copilot, hasUI: false,
    modelRegistry: { find: (provider: string) => ({ cursor, openrouter } as any)[provider], getAvailable: () => [copilot, cursor, openrouter] },
  };
  expect((await handler!(event, ctx)).continue).toBe(true);
  expect(switched).toEqual(["openrouter"]);
  delete process.env.JEV_ROUTED_SESSION;
});

test("skip an unauthenticated provider and stop when the metered provider is exhausted", async () => {
  process.env.JEV_ROUTED_SESSION = "1";
  let handler: ((event: any, context: any) => Promise<any>) | undefined;
  const switched: string[] = [];
  fallback({
    on: (name: string, callback: typeof handler) => { if (name === "agent_before_settle") handler = callback; },
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

const reply = (answers: unknown) => async () => new Response(JSON.stringify({ answers }));
const HARD = { difficulty: { type: "score", score: 1.9, confidence: 0.9 }, strict_structure: { type: "noul", noul: 0.1 } };

test("Jev's difficulty score and structure noul compose into an effort", async () => {
  expect(await chooseEffort("t", "k", reply(HARD) as any)).toBe("high");
  expect(await chooseEffort("t", "k", reply({ ...HARD, difficulty: { score: 0.2, confidence: 1 } }) as any)).toBe("medium");
});

test("nonfinite score, confidence and noul match the Python fallback", () => {
  for (const value of [NaN, Infinity, -Infinity]) {
    expect(effortFromAnswers({ difficulty: { score: value, confidence: 0.9 } })).toBe("medium");
    expect(effortFromAnswers({ difficulty: { score: 2, confidence: value } })).toBe("medium");
    expect(effortFromAnswers({ difficulty: { score: 0, confidence: 0.9 }, strict_structure: { noul: value } })).toBe("medium");
  }
  expect(effortFromAnswers({ difficulty: { score: 2, confidence: NaN }, strict_structure: { noul: 1 } })).toBe("high");
});

test("failed or unusable Jev answers continue on medium without leaking the key", async () => {
  const boom = async () => { throw new Error("Bearer secret-key leaked"); };
  expect(await chooseEffort("t", "secret-key", boom as any)).toBe("medium");
  expect(await chooseEffort("t", "k", reply({}) as any)).toBe("medium");
  expect(await chooseEffort("t", "k", reply("nope") as any)).toBe("medium");
  expect(await chooseEffort("t", "k", (async () => new Response("{}", { status: 500 })) as any)).toBe("medium");
});

test("the request asks one score and one noul in a single call", async () => {
  let sent: any;
  await chooseEffort("t", "k", (async (_url: string, init: any) => { sent = JSON.parse(init.body); return new Response(JSON.stringify({ answers: HARD })); }) as any);
  expect(Object.fromEntries(Object.entries(sent.questions).map(([name, q]: any) => [name, q.type]))).toEqual({ difficulty: "score", strict_structure: "noul" });
  expect(sent.questions.difficulty.criteria.length).toBe(3);
});

for (const item of cases as { name: string; answers: any; expected: string }[]) {
  test(`effort case: ${item.name}`, () => {
    expect(effortFromAnswers(item.answers)).toBe(item.expected);
  });
}

test("a bare single launch runs on the session's Sonnet route", () => {
  expect(workerBaseModel({ agent: "worker", task: "fix" }, "github-copilot/claude-sonnet-5.5")).toBe("github-copilot/claude-sonnet-5.5");
});

test("an explicit Sonnet route without a suffix is kept as the base", () => {
  expect(workerBaseModel({ agent: "worker", task: "x", model: "anthropic/claude-sonnet-5-5" }, "github-copilot/claude-sonnet-5.5")).toBe("anthropic/claude-sonnet-5-5");
  // Cursor is not a route (no tools there), so an explicit Cursor model gets no effort
  expect(workerBaseModel({ agent: "worker", task: "x", model: "cursor/claude-sonnet-5-5" }, "github-copilot/claude-sonnet-5.5")).toBeUndefined();
});

test("explicit suffixes, other models, workflows and management calls have no base", () => {
  const sonnet = "github-copilot/claude-sonnet-5.5";
  const cases: any[] = [
    { agent: "worker", task: "x", model: "hnn/uncensored:low" },
    { agent: "worker", task: "x", model: "nvidia/deepseek-ai/deepseek-v4.1-flash" },
    { workflowScript: "return 1" },
    { action: "list" },
    { agent: "worker" },
  ];
  for (const input of cases) expect(workerBaseModel(input, sonnet)).toBeUndefined();
  expect(workerBaseModel({ agent: "worker", task: "x" }, undefined)).toBeUndefined();
});

test("usage limits are read from the last assistant message only", () => {
  const limit = { role: "assistant", stopReason: "error", errorMessage: "429 usage limit" };
  expect(hitUsageLimit([limit])).toBe(true);
  expect(hitUsageLimit([limit, { role: "user" }])).toBe(true);
  expect(hitUsageLimit([limit, { role: "assistant", stopReason: "stop" }])).toBe(false);
  expect(hitUsageLimit([{ role: "assistant", stopReason: "error", errorMessage: "401 bad key" }])).toBe(false);
  expect(hitUsageLimit([])).toBe(false);
});

test("fallback candidates keep route order and drop exhausted or unavailable ones", () => {
  const all = ROUTES.map(([provider, id]) => `${provider}/${id}`);
  expect(fallbackCandidates(new Set(), all)).toEqual([...ROUTES]);
  expect(fallbackCandidates(new Set([all[0]]), all)).toEqual([ROUTES[1], ROUTES[2], ROUTES[3]]);
  expect(fallbackCandidates(new Set([all[0]]), [all[0], all[3]])).toEqual([ROUTES[3]]);
  expect(fallbackCandidates(new Set(all), all)).toEqual([]);
});

function workerHarness() {
  const handlers: Record<string, (event: any, context: any) => Promise<any>> = {};
  fallback({ on: (name: string, cb: any) => { handlers[name] = cb; } } as any);
  return handlers;
}
const sonnetCtx = { model: { provider: "github-copilot", id: "claude-sonnet-5.5" }, hasUI: false };

test("the key handoff is consumed at load and never stays in the environment", async () => {
  process.env.JEV_ROUTED_SESSION = "1";
  process.env.JEV_KEY_HANDOFF = "secret";
  workerHarness();
  expect(process.env.JEV_KEY_HANDOFF).toBeUndefined();
  delete process.env.JEV_ROUTED_SESSION;
});

test("a subagent launch asks Jev once and pins the chosen effort", async () => {
  process.env.JEV_ROUTED_SESSION = "1";
  process.env.JEV_KEY_HANDOFF = "secret";
  const handlers = workerHarness();
  const seen: string[] = [];
  const original = globalThis.fetch;
  globalThis.fetch = (async (_url: string, init: any) => {
    seen.push(JSON.parse(init.body).state);
    return new Response(JSON.stringify({ answers: HARD }));
  }) as any;
  try {
    const event = { toolName: "subagent", input: { agent: "worker", task: "hard refactor" } };
    await handlers.tool_call(event, sonnetCtx);
    expect(event.input).toMatchObject({ model: "github-copilot/claude-sonnet-5.5:high" });
    expect(seen).toEqual(["hard refactor"]);
    const other = { toolName: "bash", input: { command: "ls" } };
    await handlers.tool_call(other, sonnetCtx);
    expect(other.input).toEqual({ command: "ls" });
    expect(seen.length).toBe(1);
  } finally {
    globalThis.fetch = original;
    delete process.env.JEV_ROUTED_SESSION;
  }
});

test("without the handed-off key (child sessions) launches are untouched", async () => {
  process.env.JEV_ROUTED_SESSION = "1";
  delete process.env.JEV_KEY_HANDOFF;
  const handlers = workerHarness();
  const event = { toolName: "subagent", input: { agent: "worker", task: "x" } };
  expect(handlers.tool_call).toBeUndefined();
  expect(event.input).toEqual({ agent: "worker", task: "x" });
  delete process.env.JEV_ROUTED_SESSION;
});

test("the request body is pure: task truncated, one score and one noul", () => {
  const body = buildRequestBody("x".repeat(9000));
  expect(body.state.length).toBe(8000);
  expect(Object.values(body.questions).map((question) => question.type)).toEqual(["score", "noul"]);
});

test("the built-in codex agents map to the Jev-aware ones; everything else does not", () => {
  expect(redirectCodexAgent({ agent: "codex-exec", task: "x" })).toBe("codex-jev");
  expect(redirectCodexAgent({ agent: "codex-exec-writer", task: "x" })).toBe("codex-jev-writer");
  for (const input of [{ agent: "worker", task: "x" }, { agent: "codex-jev", task: "x" }, { workflowScript: "return 1" }, { action: "list" }, null, "x"]) {
    expect(redirectCodexAgent(input as any)).toBeUndefined();
  }
});

test("with the codex agents installed, launches are redirected even without a Jev key", async () => {
  process.env.JEV_ROUTED_SESSION = "1";
  process.env.JEV_CODEX_AGENTS = "1";
  delete process.env.JEV_KEY_HANDOFF;
  try {
    const handlers = workerHarness();
    const event = { toolName: "subagent", input: { agent: "codex-exec-writer", task: "x" } };
    await handlers.tool_call(event, sonnetCtx);
    expect(event.input.agent).toBe("codex-jev-writer");
    const other = { toolName: "subagent", input: { agent: "worker", task: "x" } };
    await handlers.tool_call(other, sonnetCtx);
    expect(other.input.agent).toBe("worker");
  } finally {
    delete process.env.JEV_ROUTED_SESSION;
    delete process.env.JEV_CODEX_AGENTS;
  }
});

test("without the agents installed the codex launches stay as they are", async () => {
  process.env.JEV_ROUTED_SESSION = "1";
  delete process.env.JEV_CODEX_AGENTS;
  delete process.env.JEV_KEY_HANDOFF;
  const handlers = workerHarness();
  expect(handlers.tool_call).toBeUndefined();
  delete process.env.JEV_ROUTED_SESSION;
});

test("a redirected codex launch is not given a Sonnet effort", async () => {
  process.env.JEV_ROUTED_SESSION = "1";
  process.env.JEV_CODEX_AGENTS = "1";
  process.env.JEV_KEY_HANDOFF = "secret";
  const original = globalThis.fetch;
  globalThis.fetch = (async () => { throw new Error("Jev must not be asked for a codex launch"); }) as any;
  try {
    const handlers = workerHarness();
    const event = { toolName: "subagent", input: { agent: "codex-exec", task: "x" } };
    await handlers.tool_call(event, sonnetCtx);
    expect(event.input).toEqual({ agent: "codex-jev", task: "x" });
  } finally {
    globalThis.fetch = original;
    delete process.env.JEV_ROUTED_SESSION;
    delete process.env.JEV_CODEX_AGENTS;
  }
});

test("the Claude Code subscription is tried after the other subscriptions and before the metered route", () => {
  const all = ROUTES.map(([provider, id]) => `${provider}/${id}`);
  const anthropic = "anthropic/claude-sonnet-5-5";
  expect(all.indexOf(anthropic)).toBeGreaterThan(all.indexOf("github-copilot/claude-sonnet-5.5"));
  expect(all.indexOf(anthropic)).toBeLessThan(all.indexOf("openrouter/anthropic/claude-sonnet-5.5"));
  expect(fallbackCandidates(new Set([all[0]]), all)[0]).toEqual(["anthropic", "claude-sonnet-5-5"]);
});
