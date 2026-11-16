import { afterEach, beforeEach, expect, test } from "bun:test";
import fallback, {
  ROUTES,
  buildRequestBody,
  chooseEffort,
  effortFromAnswers,
  fallbackCandidates,
  hitUsageLimit,
  isUsageLimit,
  redirectCodexAgent,
  workerBaseModel,
} from "../../config/pi/extensions/jev-sonnet-fallback";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import cases from "./jev_effort_cases.json";

// The extension decides what to register from these variables, and a dev shell
// can already carry them (Pi running under the Jev launcher exports
// JEV_ROUTED_SESSION and JEV_CODEX_AGENTS to its children). Each test sets only
// the variables it means to set, so start from a clean slate and put the
// ambient values back afterwards — otherwise a leaked JEV_CODEX_AGENTS alone
// registers the tool_call handler and the child-session test cannot pass.
const JEV_ENV = ["JEV_ROUTED_SESSION", "JEV_KEY_HANDOFF", "JEV_CODEX_AGENTS"] as const;
const ambient = new Map<string, string | undefined>();
// oxlint-disable-next-line node/no-process-env -- the tests save and restore the launcher's variables by name
const { env } = process;
const realFetch = globalThis.fetch;

beforeEach(() => {
  for (const name of JEV_ENV) {
    ambient.set(name, env[name]);
    Reflect.deleteProperty(env, name);
  }
});

afterEach(() => {
  globalThis.fetch = realFetch;
  for (const name of JEV_ENV) {
    const value = ambient.get(name);
    if (typeof value === "string") {
      env[name] = value;
    } else {
      Reflect.deleteProperty(env, name);
    }
  }
});

// ---- Fakes: only the part of Pi's API that the extension calls. ----

type Handler = (event: unknown, ctx: unknown) => Promise<unknown>;

interface Model {
  id: string;
  provider: string;
}

interface Session {
  handlers: Map<string, Handler>;
  switched: string[];
  thinking: string[];
}

interface FakeContext {
  hasUI: boolean;
  model: Model;
  modelRegistry: { find: (provider: string) => Model | undefined; getAvailable: () => Model[] };
  thinkingLevel?: string;
}

interface SettleEvent {
  context: { contextMessages: { errorMessage: string; role: string; stopReason: string }[] };
  outcome: string;
}

const COPILOT: Model = { id: "claude-sonnet-5.5", provider: "github-copilot" };
const ANTHROPIC: Model = { id: "claude-sonnet-5-5", provider: "anthropic" };
const OPENROUTER: Model = { id: "anthropic/claude-sonnet-5.5", provider: "openrouter" };
const CURSOR: Model = { id: "claude-sonnet-5-5", provider: "cursor" };
const COPILOT_ROUTE = "github-copilot/claude-sonnet-5.5";
const ANTHROPIC_ROUTE = "anthropic/claude-sonnet-5-5";
const OPENROUTER_ROUTE = "openrouter/anthropic/claude-sonnet-5.5";
const ROUTE_NAMES = ROUTES.map(([provider, id]) => `${provider}/${id}`);
const CRITERIA_COUNT = 3;
const LONG_TASK_CHARS = 9000;
const MAX_STATE_CHARS = 8000;
const HARD = {
  difficulty: { confidence: 0.9, score: 1.9, type: "score" },
  strict_structure: { noul: 0.1, type: "noul" },
};

/** Load the extension into a fake Pi that records what the extension asks of it. */
function loadExtension(): Session {
  const session: Session = { handlers: new Map(), switched: [], thinking: [] };
  const pi = {
    on: (name: string, handler: Handler): void => {
      session.handlers.set(name, handler);
    },
    setModel: async (model: Model): Promise<boolean> => {
      session.switched.push(model.provider);
      return true;
    },
    setThinkingLevel: (level: string): void => {
      session.thinking.push(level);
    },
  };
  // oxlint-disable-next-line typescript/no-unsafe-type-assertion -- the fake implements only the three methods of Pi's API that the extension calls
  fallback(pi as unknown as ExtensionAPI);
  return session;
}

function handlerOf(session: Session, name: string): Handler {
  const handler = session.handlers.get(name);
  if (!handler) {
    throw new Error(`the extension registered no ${name} handler`);
  }
  return handler;
}

/** A session on `model`, where Pi's registry holds the `authenticated` models. */
const contextOn = (model: Model, authenticated: readonly Model[], thinkingLevel?: string): FakeContext => ({
  hasUI: false,
  model,
  modelRegistry: {
    find: (provider) => authenticated.find((candidate) => candidate.provider === provider),
    getAvailable: () => [...authenticated],
  },
  thinkingLevel,
});

const failedWith = (errorMessage: string): SettleEvent => ({
  context: { contextMessages: [{ errorMessage, role: "assistant", stopReason: "error" }] },
  outcome: "error",
});

/** A `fetch` that answers every request with `respond`, which sees the request's options. */
const fetchStub = (respond: (init?: RequestInit) => Promise<Response>): typeof fetch =>
  Object.assign(async (_url: unknown, init?: RequestInit) => respond(init), {
    preconnect: (url: string | URL): void => {
      realFetch.preconnect(url);
    },
  });

const answering = (answers: unknown): typeof fetch => fetchStub(async () => Response.json({ answers }));

const failing = (message: string): typeof fetch => fetchStub(async () => {
    throw new Error(message);
  });

function bodyOf(init?: RequestInit): unknown {
  const body = init?.body;
  if (typeof body !== "string") {
    throw new TypeError("the request body is not a string");
  }
  return JSON.parse(body);
}

// ---- Usage limits ----

const LIMITS = [
  "429 quota exceeded",
  "HTTP/2 429",
  "statusCode=429",
  "Error: status code 429",
  '{"status":429}',
  '{"error":{"type":"rate_limit_error"}}',
  '{"error":{"code":"insufficient_quota"}}',
  "RESOURCE_EXHAUSTED",
  "rate_limit_error: provider stopped",
];
const NOT_LIMITS = [
  "Request ID 429 failed: authentication error (401)",
  "Rate limiter configuration is invalid (400)",
  "quota exceeded",
  "rate limit reached",
  "no usage limit exceeded",
  "not RESOURCE_EXHAUSTED",
  "4290 quota exceeded",
  "HTTP 429.1",
  "HTTP 429/401",
  "statusCode=4291",
  'HTTP 400: fixture says "HTTP 429: usage limit reached"',
  '401 fixture says "quota exceeded"',
  '403 fixture says "rate limit reached"',
  'HTTP 500: fixture says "429"',
  "HTTP 429, statusCode=401",
  "rate_limit_error: HTTP 401",
  '{"status":401,"error":{"type":"rate_limit_error"}}',
  '{"status":429,"error":{"status":401}}',
  '{"error":{"type":"authentication_error","message":"HTTP 429"}}',
  '{"status":true,"error":{"type":"rate_limit_error"}}',
];
const AMBIGUOUS = [
  "Request ID 429 failed: authentication error (401)",
  "Rate limiter configuration is invalid (400)",
  "quota exceeded",
  "HTTP 429, statusCode=401",
];

test("only provider usage limits trigger a switch", () => {
  expect(isUsageLimit("HTTP 429: usage limit reached")).toBe(true);
  expect(isUsageLimit("401 invalid authentication")).toBe(false);
  expect(isUsageLimit("network timeout")).toBe(false);
});

test("only explicit status or machine error kinds count as provider limits", () => {
  expect(LIMITS.filter((message) => !isUsageLimit(message))).toEqual([]);
  expect(NOT_LIMITS.filter((message) => isUsageLimit(message))).toEqual([]);
});

test("usage limits are read from the last assistant message only", () => {
  const limit = { errorMessage: "429 usage limit", role: "assistant", stopReason: "error" };
  expect(hitUsageLimit([limit])).toBe(true);
  expect(hitUsageLimit([limit, { role: "user" }])).toBe(true);
  expect(hitUsageLimit([limit, { role: "assistant", stopReason: "stop" }])).toBe(false);
  expect(hitUsageLimit([{ errorMessage: "401 bad key", role: "assistant", stopReason: "error" }])).toBe(false);
  expect(hitUsageLimit([])).toBe(false);
});

// ---- Routes ----

test("subscription candidates precede metered candidate", () => {
  expect(ROUTES.map(([provider]) => provider)).toEqual(["github-copilot", "anthropic", "openrouter"]);
});

test("the Claude Code subscription is tried after the other subscriptions and before the metered route", () => {
  expect(ROUTE_NAMES.indexOf(ANTHROPIC_ROUTE)).toBeGreaterThan(ROUTE_NAMES.indexOf(COPILOT_ROUTE));
  expect(ROUTE_NAMES.indexOf(ANTHROPIC_ROUTE)).toBeLessThan(ROUTE_NAMES.indexOf(OPENROUTER_ROUTE));
  expect(fallbackCandidates(new Set([COPILOT_ROUTE]), ROUTE_NAMES).at(0)).toEqual(["anthropic", "claude-sonnet-5-5"]);
});

test("fallback candidates keep route order and drop exhausted or unavailable ones", () => {
  const [copilot, anthropic, openrouter] = ROUTES;
  expect(fallbackCandidates(new Set(), ROUTE_NAMES)).toEqual([copilot, anthropic, openrouter]);
  expect(fallbackCandidates(new Set([COPILOT_ROUTE]), ROUTE_NAMES)).toEqual([anthropic, openrouter]);
  expect(fallbackCandidates(new Set([COPILOT_ROUTE]), [COPILOT_ROUTE, OPENROUTER_ROUTE])).toEqual([openrouter]);
  expect(fallbackCandidates(new Set(ROUTE_NAMES), ROUTE_NAMES)).toEqual([]);
});

// ---- Provider fallback ----

test("an ambiguous error neither switches nor exhausts a route", async () => {
  process.env.JEV_ROUTED_SESSION = "1";
  const session = loadExtension();
  const settle = handlerOf(session, "agent_before_settle");
  const authenticated = [COPILOT, OPENROUTER];
  const onCopilot = contextOn(COPILOT, authenticated, "high");
  const results = await Promise.all(AMBIGUOUS.map(async (message) => settle(failedWith(message), onCopilot)));
  expect(new Set(results).size).toBe(1);
  expect(results.at(0)).toBeUndefined();
  expect(session.switched).toEqual([]);
  expect(session.thinking).toEqual([]);
  // Copilot must still be eligible: only the genuine Router limit exhausts a route.
  const onRouter = contextOn(OPENROUTER, authenticated, "high");
  const result = await settle(failedWith("HTTP 429: provider quota exceeded"), onRouter);
  expect(session.switched).toEqual(["github-copilot"]);
  expect(session.thinking).toEqual(["high"]);
  expect(result).toMatchObject({ continue: true });
});

test("after a subscription limit, continue on the next authenticated provider", async () => {
  process.env.JEV_ROUTED_SESSION = "1";
  const session = loadExtension();
  const settle = handlerOf(session, "agent_before_settle");
  const authenticated = [COPILOT, ANTHROPIC, OPENROUTER];
  const event = failedWith("HTTP 429: usage limit exceeded");
  const result = await settle(event, contextOn(COPILOT, authenticated, "medium"));
  expect(session.switched).toEqual(["anthropic"]);
  expect(result).toMatchObject({ continue: true, entries: [{ type: "custom_message" }] });
  await settle(event, contextOn(ANTHROPIC, authenticated, "medium"));
  expect(session.switched).toEqual(["anthropic", "openrouter"]);
  expect(session.thinking).toEqual(["medium", "medium"]);
});

test("Cursor is never a fallback, even when authenticated: Pi gives that provider no tools", async () => {
  process.env.JEV_ROUTED_SESSION = "1";
  const session = loadExtension();
  const settle = handlerOf(session, "agent_before_settle");
  const onCopilot = contextOn(COPILOT, [COPILOT, CURSOR, OPENROUTER]);
  const result = await settle(failedWith("429 quota exceeded"), onCopilot);
  expect(result).toMatchObject({ continue: true });
  expect(session.switched).toEqual(["openrouter"]);
});

test("skip an unauthenticated provider and stop when the metered provider is exhausted", async () => {
  process.env.JEV_ROUTED_SESSION = "1";
  const session = loadExtension();
  const settle = handlerOf(session, "agent_before_settle");
  const authenticated = [COPILOT, OPENROUTER];
  const event = failedWith("429 quota exceeded");
  const first = await settle(event, contextOn(COPILOT, authenticated));
  expect(first).toMatchObject({ continue: true });
  expect(session.switched).toEqual(["openrouter"]);
  const second = await settle(event, contextOn(OPENROUTER, authenticated));
  expect(second).toBeUndefined();
});

// ---- Jev effort ----

test("Jev's difficulty score and structure noul compose into an effort", async () => {
  const easy = { difficulty: { confidence: 1, score: 0.2 }, strict_structure: HARD.strict_structure };
  expect(await chooseEffort("t", "k", answering(HARD))).toBe("high");
  expect(await chooseEffort("t", "k", answering(easy))).toBe("medium");
});

test("nonfinite score, confidence and noul match the Python fallback", () => {
  for (const value of [Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY]) {
    expect(effortFromAnswers({ difficulty: { confidence: 0.9, score: value } })).toBe("medium");
    expect(effortFromAnswers({ difficulty: { confidence: value, score: 2 } })).toBe("medium");
    expect(effortFromAnswers({ difficulty: { confidence: 0.9, score: 0 }, strict_structure: { noul: value } })).toBe(
      "medium",
    );
  }
  const structured = { difficulty: { confidence: Number.NaN, score: 2 }, strict_structure: { noul: 1 } };
  expect(effortFromAnswers(structured)).toBe("high");
});

test("failed or unusable Jev answers continue on medium without leaking the key", async () => {
  const serverError = fetchStub(async () => new Response("{}", { status: 500 }));
  expect(await chooseEffort("t", "secret-key", failing("Bearer secret-key leaked"))).toBe("medium");
  expect(await chooseEffort("t", "k", answering({}))).toBe("medium");
  expect(await chooseEffort("t", "k", answering("nope"))).toBe("medium");
  expect(await chooseEffort("t", "k", serverError)).toBe("medium");
});

test("the request asks one score and one noul in a single call", async () => {
  const sent: unknown[] = [];
  const recording = fetchStub(async (init) => {
    sent.push(bodyOf(init));
    return Response.json({ answers: HARD });
  });
  await chooseEffort("t", "k", recording);
  expect(sent).toHaveLength(1);
  expect(sent).toMatchObject([{ questions: { difficulty: { type: "score" }, strict_structure: { type: "noul" } } }]);
  expect(buildRequestBody("t").questions.difficulty.criteria).toHaveLength(CRITERIA_COUNT);
});

for (const item of cases) {
  test(`effort case: ${item.name}`, () => {
    expect<string>(effortFromAnswers(item.answers)).toBe(item.expected);
  });
}

test("the request body is pure: task truncated, one score and one noul", () => {
  const body = buildRequestBody("x".repeat(LONG_TASK_CHARS));
  expect(body.state).toHaveLength(MAX_STATE_CHARS);
  expect(Object.values(body.questions).map((question) => question.type)).toEqual(["score", "noul"]);
});

// ---- Worker launches ----

test("a bare single launch runs on the session's Sonnet route", () => {
  expect(workerBaseModel({ agent: "worker", task: "fix" }, COPILOT_ROUTE)).toBe(COPILOT_ROUTE);
});

test("an explicit Sonnet route without a suffix is kept as the base", () => {
  expect(workerBaseModel({ agent: "worker", model: ANTHROPIC_ROUTE, task: "x" }, COPILOT_ROUTE)).toBe(ANTHROPIC_ROUTE);
  // Cursor is not a route (no tools there), so an explicit Cursor model gets no effort
  const onCursor = { agent: "worker", model: "cursor/claude-sonnet-5-5", task: "x" };
  expect(workerBaseModel(onCursor, COPILOT_ROUTE)).toBeUndefined();
});

test("explicit suffixes, other models, workflows and management calls have no base", () => {
  const inputs = [
    { agent: "worker", model: "hnn/uncensored:low", task: "x" },
    { agent: "worker", model: "nvidia/deepseek-ai/deepseek-v4.1-flash", task: "x" },
    { workflowScript: "return 1" },
    { action: "list" },
    { agent: "worker" },
  ];
  expect(inputs.filter((input) => typeof workerBaseModel(input, COPILOT_ROUTE) === "string")).toEqual([]);
  expect(workerBaseModel({ agent: "worker", task: "x" })).toBeUndefined();
});

test("the built-in codex agents map to the Jev-aware ones; everything else does not", () => {
  expect(redirectCodexAgent({ agent: "codex-exec", task: "x" })).toBe("codex-jev");
  expect(redirectCodexAgent({ agent: "codex-exec-writer", task: "x" })).toBe("codex-jev-writer");
  const others = [
    { agent: "worker", task: "x" },
    { agent: "codex-jev", task: "x" },
    { workflowScript: "return 1" },
    { action: "list" },
    // oxlint-disable-next-line unicorn/no-null -- a launch whose input is null must be left alone
    null,
    "x",
  ];
  expect(others.filter((input) => typeof redirectCodexAgent(input) === "string")).toEqual([]);
});

const SONNET_SESSION = contextOn(COPILOT, [COPILOT]);

test("the key handoff is consumed at load and never stays in the environment", () => {
  process.env.JEV_ROUTED_SESSION = "1";
  process.env.JEV_KEY_HANDOFF = "secret";
  loadExtension();
  expect(process.env.JEV_KEY_HANDOFF).toBeUndefined();
});

test("a subagent launch asks Jev once and pins the chosen effort", async () => {
  process.env.JEV_ROUTED_SESSION = "1";
  process.env.JEV_KEY_HANDOFF = "secret";
  const toolCall = handlerOf(loadExtension(), "tool_call");
  const seen: unknown[] = [];
  globalThis.fetch = fetchStub(async (init) => {
    seen.push(bodyOf(init));
    return Response.json({ answers: HARD });
  });
  const launch = { input: { agent: "worker", task: "hard refactor" }, toolName: "subagent" };
  await toolCall(launch, SONNET_SESSION);
  expect(launch.input).toMatchObject({ model: "github-copilot/claude-sonnet-5.5:high" });
  expect(seen).toMatchObject([{ state: "hard refactor" }]);
  const other = { input: { command: "ls" }, toolName: "bash" };
  await toolCall(other, SONNET_SESSION);
  expect(other.input).toEqual({ command: "ls" });
  expect(seen).toHaveLength(1);
});

test("without the handed-off key (child sessions) launches are untouched", () => {
  process.env.JEV_ROUTED_SESSION = "1";
  expect(loadExtension().handlers.get("tool_call")).toBeUndefined();
});

test("with the codex agents installed, launches are redirected even without a Jev key", async () => {
  process.env.JEV_ROUTED_SESSION = "1";
  process.env.JEV_CODEX_AGENTS = "1";
  const toolCall = handlerOf(loadExtension(), "tool_call");
  const codex = { input: { agent: "codex-exec-writer", task: "x" }, toolName: "subagent" };
  await toolCall(codex, SONNET_SESSION);
  expect(codex.input.agent).toBe("codex-jev-writer");
  const worker = { input: { agent: "worker", task: "x" }, toolName: "subagent" };
  await toolCall(worker, SONNET_SESSION);
  expect(worker.input.agent).toBe("worker");
});

test("without the agents installed the codex launches stay as they are", () => {
  process.env.JEV_ROUTED_SESSION = "1";
  expect(loadExtension().handlers.get("tool_call")).toBeUndefined();
});

test("a redirected codex launch is not given a Sonnet effort", async () => {
  process.env.JEV_ROUTED_SESSION = "1";
  process.env.JEV_CODEX_AGENTS = "1";
  process.env.JEV_KEY_HANDOFF = "secret";
  globalThis.fetch = failing("Jev must not be asked for a codex launch");
  const toolCall = handlerOf(loadExtension(), "tool_call");
  const launch = { input: { agent: "codex-exec", task: "x" }, toolName: "subagent" };
  await toolCall(launch, SONNET_SESSION);
  expect(launch.input).toEqual({ agent: "codex-jev", task: "x" });
});
