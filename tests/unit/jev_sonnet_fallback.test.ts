import { expect, test } from "bun:test";
import cases from "./jev_effort_cases.json";
import fallback, { buildRequestBody, chooseEffort, effortFromAnswers, fallbackCandidates, hitUsageLimit, isUsageLimit, ROUTES, workerBaseModel } from "../../config/pi/extensions/jev-sonnet-fallback";

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
    on: (name: string, callback: typeof handler) => { if (name === "agent_before_settle") handler = callback; },
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
  expect(workerBaseModel({ agent: "worker", task: "x", model: "cursor/claude-sonnet-5-5" }, "github-copilot/claude-sonnet-5.5")).toBe("cursor/claude-sonnet-5-5");
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
  expect(fallbackCandidates(new Set([all[0]]), all)).toEqual([ROUTES[1], ROUTES[2]]);
  expect(fallbackCandidates(new Set([all[0]]), [all[0], all[2]])).toEqual([ROUTES[2]]);
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
