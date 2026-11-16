// dotfiles-managed: jev-sonnet-fallback
// Pi links this file into the agent dir, so it must import Pi's package for
// its types only: a value import would resolve to the dev dependency in this
// checkout instead of the running Pi (ADR-0059, ADR-0079).
import type { AgentBeforeSettleEventResult, ExtensionAPI, ExtensionContext } from "@earendil-works/pi-coding-agent";

// Other subscriptions first, then the Claude Code subscription (kept for last so it is
// left for Claude Code itself), then the metered route. Pi's registry only exposes
// authenticated models. Cursor is not a route: Pi hands that provider no tools, so a
// session there cannot launch a worker, run a command or edit a file.
const ROUTES = [
  ["github-copilot", "claude-sonnet-5.5"],
  ["anthropic", "claude-sonnet-5-5"],
  ["openrouter", "anthropic/claude-sonnet-5.5"],
] as const;

type Route = (typeof ROUTES)[number];
type Effort = "high" | "medium";
type Fields = Record<string, unknown>;

// ---- Functional core: pure decisions over plain data. No env, network or Pi calls. ----

const LIMIT_KINDS = new Set(["rate_limit_error", "rate_limit_exceeded", "insufficient_quota", "RESOURCE_EXHAUSTED"]);
const TOO_MANY_REQUESTS = 429;
const STATUS_KEYS = ["status", "statusCode"] as const;
const STATUS_CODE = /^[1-5]\d{2}$/u;
const STATUS_PREFIX =
  /^(?:Error:\s*)?(?:(?:HTTP(?:\/[\d.]+)?|status(?:Code|\s+code)?)\s*[:=]?\s*)?(?<status>[1-5]\d{2})\b(?![./]\d)/iu;
const EXPLICIT_STATUS = /\b(?:HTTP(?:\/[\d.]+)?|status(?:Code|\s+code)?)\s*[:=]?\s*(?<status>[1-5]\d{2})\b(?![./]\d)/giu;
// Exact leading machine identifiers, not natural-language 'quota exceeded'.
const LEADING_LIMIT_KIND = /^(?:rate_limit_error|rate_limit_exceeded|insufficient_quota|RESOURCE_EXHAUSTED)(?:\s*:|\s*$)/u;

const isFields = (value: unknown): value is Fields =>
  Boolean(value) && typeof value === "object" && !Array.isArray(value);

/** The value as an object; anything else reads as an object with no fields. */
function fieldsOf(value: unknown): Fields {
  if (isFields(value)) {
    return value;
  }
  return {};
}

const isLimitKind = (value: unknown): boolean => typeof value === "string" && LIMIT_KINDS.has(value);

const isStatusCode = (value: unknown): boolean =>
  (typeof value === "number" || typeof value === "string") && STATUS_CODE.test(String(value));

/** JSON text as a value. Text that is not JSON comes back as it is, which is never an object. */
function parseJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function statusOf(match: Readonly<RegExpExecArray>): number {
  return Number(fieldsOf(match.groups).status);
}

/** A structured provider error: known machine fields only, never the message text. */
function isStructuredLimit(payload: Readonly<Fields>): boolean {
  const details = [payload];
  if (isFields(payload.error)) {
    details.push(payload.error);
  }
  const statuses = details
    .flatMap((detail) => STATUS_KEYS.filter((key) => key in detail).map((key) => detail[key]))
    .filter((value) => !isLimitKind(value));
  if (!statuses.every((status) => isStatusCode(status))) {
    return false;
  }
  // Authentication/server errors and conflicting statuses must not switch routes.
  if (statuses.length > 0) {
    return statuses.every((status) => Number(status) === TOO_MANY_REQUESTS);
  }
  return details.some((detail) => [detail.type, detail.code, detail.status].some((value) => isLimitKind(value)));
}

/** A textual provider diagnostic: an explicit status or a leading machine identifier. */
function isTextualLimit(text: string): boolean {
  const explicit = [...text.matchAll(EXPLICIT_STATUS)].map((match) => statusOf(match));
  if (explicit.some((status) => status !== TOO_MANY_REQUESTS)) {
    return false;
  }
  const prefix = STATUS_PREFIX.exec(text);
  if (prefix) {
    return statusOf(prefix) === TOO_MANY_REQUESTS;
  }
  return LEADING_LIMIT_KIND.test(text);
}

function isUsageLimit(message: unknown): boolean {
  if (typeof message !== "string") {
    return false;
  }
  // Never search a JSON message or prompt for quota words.
  const payload = parseJson(message);
  if (isFields(payload)) {
    return isStructuredLimit(payload);
  }
  return isTextualLimit(message.trim());
}

const isAssistantMessage = (message: unknown): message is Fields => isFields(message) && message.role === "assistant";

/** Did the last assistant message end in a provider usage limit? */
function hitUsageLimit(messages: readonly unknown[]): boolean {
  const last = messages.findLast((message) => isAssistantMessage(message));
  if (last?.stopReason !== "error") {
    return false;
  }
  return isUsageLimit(last.errorMessage ?? "");
}

const routeName = ([provider, id]: Route): string => `${provider}/${id}`;

/** Routes still worth trying, in preference order: not exhausted and authenticated. */
function fallbackCandidates(exhausted: ReadonlySet<string>, available: readonly string[]): Route[] {
  return ROUTES.filter((route) => !exhausted.has(routeName(route)) && available.includes(routeName(route)));
}

const JEV_URL = "https://api.typesafe.ai/v1/systemone";
const JEV_TIMEOUT_MS = 5000;
const MAX_STATE_CHARS = 8000;
// Same questions and thresholds as scripts/jev_launch.py (tests/unit/jev_effort_cases.json
// keeps both in step). Jev answers atomic questions; this code combines them.
const QUESTIONS = {
  difficulty: {
    criteria: [
      "Small, well-specified change or lookup with a clear finish line, such as a rename, a typo, or running one command.",
      "Routine multi-step engineering with a known approach, such as adding a test, a simple feature, or a focused bug fix.",
      "Hard or open-ended engineering: unclear cause, cross-cutting design, many files or services, migrations, or long-running multistep tool use.",
    ],
    instructions: "How demanding is this coding-agent task for the model that performs it?",
    type: "score",
  },
  strict_structure: {
    instructions:
      "Does the task require producing strictly structured output, such as a JSON schema, a typed contract, or a machine-checked format, where a formatting mistake would break a consumer?",
    type: "noul",
  },
} as const;
// Nearest level is the top of the three-level difficulty scale.
const HARD_SCORE = 1.5;
// Acting on a false yes costs thinking tokens, so lean high.
const STRICT_STRUCTURE = 0.7;
// Below this Jev is saying "I don't know"; keep the default.
const CONFIDENCE_FLOOR = 0.5;
const SUFFIX = /:(?:off|minimal|low|medium|high|xhigh|max)$/u;
// A workflow or management call: its owner already decided.
const OWNER_DECIDED_KEYS = ["action", "workflow", "workflowScript", "workflowScriptPath"] as const;
const CODEX_AGENTS = new Map([
  ["codex-exec", "codex-jev"],
  ["codex-exec-writer", "codex-jev-writer"],
]);

interface JevRequest {
  model: string;
  questions: typeof QUESTIONS;
  state: string;
}

const isSonnetRoute = (model: string): boolean => ROUTES.some((route) => routeName(route) === model);

const isFiniteNumber = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);

const buildRequestBody = (task: string): JevRequest => ({
  model: "jev-latest",
  questions: QUESTIONS,
  state: task.slice(0, MAX_STATE_CHARS),
});

/** Compose Jev's typed answers into an effort; anything unusable means medium. */
function effortFromAnswers(answers: unknown): Effort {
  const questions = fieldsOf(answers);
  const { noul } = fieldsOf(questions.strict_structure);
  if (isFiniteNumber(noul) && noul >= STRICT_STRUCTURE) {
    return "high";
  }
  const { confidence, score } = fieldsOf(questions.difficulty);
  if (!isFiniteNumber(score) || !isFiniteNumber(confidence) || confidence < CONFIDENCE_FLOOR) {
    return "medium";
  }
  if (score >= HARD_SCORE) {
    return "high";
  }
  return "medium";
}

/** A direct subagent launch, as opposed to a workflow or management call. */
const isDirectLaunch = (input: unknown): input is Fields =>
  isFields(input) && !OWNER_DECIDED_KEYS.some((key) => Boolean(input[key]));

/**
 * The Sonnet route a direct subagent launch should run on, before any effort suffix.
 * A launch that names another model, carries its own suffix, or runs as a
 * workflow/management call has none: its owner already decided.
 */
function workerBaseModel(input: unknown, sessionModel?: string): string | undefined {
  if (!isDirectLaunch(input) || typeof input.agent !== "string" || typeof input.task !== "string") {
    return;
  }
  const model = input.model ?? sessionModel;
  if (typeof model !== "string" || SUFFIX.test(model) || !isSonnetRoute(model)) {
    return;
  }
  return model;
}

/** The Jev-aware Codex agent for a direct launch of a built-in one, which cannot choose a model. */
function redirectCodexAgent(input: unknown): string | undefined {
  if (!isDirectLaunch(input) || typeof input.agent !== "string") {
    return;
  }
  return CODEX_AGENTS.get(input.agent);
}

// ---- Imperative shell: the only code that touches env, network and Pi. ----

/** One bounded Jev call per worker launch. Any failure keeps medium; error text is never surfaced. */
async function chooseEffort(task: string, key: string, fetchImpl: typeof fetch = fetch): Promise<Effort> {
  try {
    const response = await fetchImpl(JEV_URL, {
      body: JSON.stringify(buildRequestBody(task)),
      headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
      method: "POST",
      signal: AbortSignal.timeout(JEV_TIMEOUT_MS),
    });
    if (!response.ok) {
      return "medium";
    }
    const reply: unknown = await response.json();
    return effortFromAnswers(fieldsOf(reply).answers);
  } catch {
    return "medium";
  }
}

function sessionModelName(ctx: ExtensionContext): string | undefined {
  const { model } = ctx;
  if (!model) {
    return;
  }
  return `${model.provider}/${model.id}`;
}

/** Send a built-in Codex agent to its Jev-aware replacement. True when the launch was redirected. */
function redirectLaunch(input: Fields): boolean {
  const codex = redirectCodexAgent(input);
  if (typeof codex !== "string") {
    return false;
  }
  // The codex-jev agent asks Jev for the gpt-6 model and effort itself.
  input.agent = codex;
  return true;
}

/** Ask Jev once and pin the chosen effort on a direct worker launch. */
async function pinEffort(input: Fields, ctx: ExtensionContext, jevKey: string): Promise<void> {
  const base = workerBaseModel(input, sessionModelName(ctx));
  if (typeof base !== "string" || typeof input.task !== "string") {
    return;
  }
  const effort = await chooseEffort(input.task, jevKey);
  input.model = `${base}:${effort}`;
  if (ctx.hasUI) {
    ctx.ui.notify(`Jev worker effort: ${effort}`, "info");
  }
}

function registerWorkerLaunches(pi: ExtensionAPI, jevKey: string, redirectCodex: boolean): void {
  pi.on("tool_call", async (event, ctx) => {
    const input: unknown = event.input;
    if (event.toolName !== "subagent" || !isFields(input)) {
      return;
    }
    if (redirectCodex && redirectLaunch(input)) {
      return;
    }
    if (jevKey !== "") {
      await pinEffort(input, ctx, jevKey);
    }
  });
}

/** The first candidate route Pi accepts, tried one at a time in preference order. */
async function switchRoute(
  pi: ExtensionAPI,
  ctx: ExtensionContext,
  candidates: readonly Route[],
): Promise<Route | undefined> {
  const [route, ...rest] = candidates;
  if (!route) {
    return;
  }
  const [provider, modelId] = route;
  // oxlint-disable-next-line unicorn/no-array-method-this-argument -- Pi's registry lookup by (provider, id), not Array.prototype.find
  const model = ctx.modelRegistry.find(provider, modelId);
  if (model && (await pi.setModel(model))) {
    return route;
  }
  return switchRoute(pi, ctx, rest);
}

/** Tell the user where the session went, and keep its effort on the new route. */
function settleOnRoute(pi: ExtensionAPI, ctx: ExtensionContext, switched: { current: string; route: Route | undefined }): void {
  const { current, route } = switched;
  if (!route) {
    if (ctx.hasUI) {
      ctx.ui.notify(`Sonnet provider limit: ${current}; no alternate provider available`, "error");
    }
    return;
  }
  // Preserve the fixed effort chosen before the session, even across providers.
  if (ctx.thinkingLevel) {
    pi.setThinkingLevel(ctx.thinkingLevel);
  }
  if (ctx.hasUI) {
    ctx.ui.notify(`Sonnet provider limit: ${current} → ${routeName(route)}`, "warning");
  }
}

/**
 * An error ends with an assistant message; append a context-visible boundary
 * so Pi can make a fresh request rather than dead-end.
 */
const retryOnNewProvider = (): AgentBeforeSettleEventResult => ({
  continue: true,
  entries: [
    {
      content:
        "The previous provider hit a usage limit. Retry the interrupted request on the new provider; do not repeat completed tool actions.",
      customType: "jev-provider-switch",
      display: false,
      type: "custom_message",
    },
  ],
});

/** After a usage limit on a Sonnet route, continue the request on the next authenticated route. */
function registerProviderFallback(pi: ExtensionAPI): void {
  const exhausted = new Set<string>();
  pi.on("agent_before_settle", async (event, ctx): Promise<AgentBeforeSettleEventResult | undefined> => {
    const current = sessionModelName(ctx) ?? "";
    if (event.outcome !== "error" || !isSonnetRoute(current) || !hitUsageLimit(event.context.contextMessages)) {
      return;
    }
    exhausted.add(current);
    const available = ctx.modelRegistry.getAvailable().map((model) => `${model.provider}/${model.id}`);
    const route = await switchRoute(pi, ctx, fallbackCandidates(exhausted, available));
    settleOnRoute(pi, ctx, { current, route });
    if (route) {
      return retryOnNewProvider();
    }
  });
}

export {
  ROUTES,
  buildRequestBody,
  chooseEffort,
  effortFromAnswers,
  fallbackCandidates,
  hitUsageLimit,
  isUsageLimit,
  redirectCodexAgent,
  workerBaseModel,
};

export default function jevSonnetFallback(pi: ExtensionAPI): void {
  // The extension may be installed globally; only the opt-in launcher enables it.
  if (process.env.JEV_ROUTED_SESSION !== "1") {
    return;
  }
  // The launcher hands the key to this process only. Take it now so neither the
  // bash tool nor child sessions inherit it; children then leave launches alone.
  const jevKey = process.env.JEV_KEY_HANDOFF ?? "";
  delete process.env.JEV_KEY_HANDOFF;
  // Set by the launcher only when the codex-jev agents are installed.
  const redirectCodex = process.env.JEV_CODEX_AGENTS === "1";
  if (jevKey !== "" || redirectCodex) {
    registerWorkerLaunches(pi, jevKey, redirectCodex);
  }
  registerProviderFallback(pi);
}
