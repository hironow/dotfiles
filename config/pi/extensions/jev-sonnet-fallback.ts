// dotfiles-managed: jev-sonnet-fallback
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

// Other subscriptions first, then the Claude Code subscription (kept for last so it is
// left for Claude Code itself), then the metered route. Pi's registry only exposes
// authenticated models. Cursor is not a route: Pi hands that provider no tools, so a
// session there cannot launch a worker, run a command or edit a file.
export const ROUTES = [
  ["github-copilot", "claude-sonnet-5.5"],
  ["anthropic", "claude-sonnet-5-5"],
  ["openrouter", "anthropic/claude-sonnet-5.5"],
] as const;

// ---- Functional core: pure decisions over plain data. No env, network or Pi calls. ----

const LIMIT_KINDS = new Set(["rate_limit_error", "rate_limit_exceeded", "insufficient_quota", "RESOURCE_EXHAUSTED"]);
const errorObject = (value: unknown): value is Record<string, unknown> => !!value && typeof value === "object" && !Array.isArray(value);

export function isUsageLimit(message: string): boolean {
  if (typeof message !== "string") return false;
  // Known machine fields only; never search a JSON message/prompt for quota words.
  let payload: unknown;
  try { payload = JSON.parse(message); } catch { /* textual provider diagnostic */ }
  if (errorObject(payload)) {
    const details = [payload, ...(errorObject(payload.error) ? [payload.error] : [])];
    const statuses: number[] = [];
    for (const detail of details) {
      for (const key of ["status", "statusCode"]) {
        if (!(key in detail)) continue;
        const value = detail[key];
        if (typeof value === "string" && LIMIT_KINDS.has(value)) continue;
        if (typeof value !== "number" && typeof value !== "string") return false;
        if (!/^[1-5]\d{2}$/.test(String(value))) return false;
        statuses.push(Number(value));
      }
    }
    // Authentication/server errors and conflicting statuses must not switch routes.
    if (statuses.length) return statuses.every(status => status === 429);
    return details.some(detail => [detail.type, detail.code, detail.status].some(value => typeof value === "string" && LIMIT_KINDS.has(value)));
  }
  const text = message.trim();
  const statusPrefix = /^(?:Error:\s*)?(?:(?:HTTP(?:\/[\d.]+)?|status(?:Code|\s+code)?)\s*[:=]?\s*)?([1-5]\d{2})\b(?![./]\d)/i.exec(text);
  const explicitStatuses = [...text.matchAll(/\b(?:HTTP(?:\/[\d.]+)?|status(?:Code|\s+code)?)\s*[:=]?\s*([1-5]\d{2})\b(?![./]\d)/gi)].map(match => Number(match[1]));
  if (explicitStatuses.some(status => status !== 429)) return false;
  if (statusPrefix) return Number(statusPrefix[1]) === 429;
  // Exact leading machine identifiers, not natural-language 'quota exceeded'.
  return /^(?:rate_limit_error|rate_limit_exceeded|insufficient_quota|RESOURCE_EXHAUSTED)(?:\s*:|\s*$)/.test(text);
}

/** Did the last assistant message end in a provider usage limit? */
export function hitUsageLimit(messages: readonly any[]): boolean {
  const last = [...messages].reverse().find((message) => message.role === "assistant");
  return !!last && last.stopReason === "error" && isUsageLimit(last.errorMessage ?? "");
}

/** Routes still worth trying, in preference order: not exhausted and authenticated. */
export function fallbackCandidates(exhausted: ReadonlySet<string>, available: readonly string[]) {
  return ROUTES.filter(([provider, id]) => !exhausted.has(`${provider}/${id}`) && available.includes(`${provider}/${id}`));
}

const JEV_URL = "https://api.typesafe.ai/v1/systemone";
// Same questions and thresholds as scripts/jev_launch.py (tests/unit/jev_effort_cases.json
// keeps both in step). Jev answers atomic questions; this code combines them.
const QUESTIONS = {
  difficulty: {
    type: "score",
    instructions: "How demanding is this coding-agent task for the model that performs it?",
    criteria: [
      "Small, well-specified change or lookup with a clear finish line, such as a rename, a typo, or running one command.",
      "Routine multi-step engineering with a known approach, such as adding a test, a simple feature, or a focused bug fix.",
      "Hard or open-ended engineering: unclear cause, cross-cutting design, many files or services, migrations, or long-running multistep tool use.",
    ],
  },
  strict_structure: {
    type: "noul",
    instructions: "Does the task require producing strictly structured output, such as a JSON schema, a typed contract, or a machine-checked format, where a formatting mistake would break a consumer?",
  },
};
const HARD_SCORE = 1.5; // Nearest level is the top of the three-level difficulty scale.
const STRICT_STRUCTURE = 0.7; // Acting on a false yes costs thinking tokens, so lean high.
const CONFIDENCE_FLOOR = 0.5; // Below this Jev is saying "I don't know"; keep the default.
const SUFFIX = /:(off|minimal|low|medium|high|xhigh|max)$/;
const isSonnetRoute = (model: string) => ROUTES.some(([provider, id]) => `${provider}/${id}` === model);
const num = (value: unknown): number | undefined => (typeof value === "number" && Number.isFinite(value) ? value : undefined);

export const buildRequestBody = (task: string) => ({ model: "jev-latest", state: task.slice(0, 8000), questions: QUESTIONS });

/** Compose Jev's typed answers into an effort; anything unusable means medium. */
export function effortFromAnswers(answers: any): "medium" | "high" {
  const noul = num(answers?.strict_structure?.noul);
  if (noul !== undefined && noul >= STRICT_STRUCTURE) return "high";
  const score = num(answers?.difficulty?.score);
  const confidence = num(answers?.difficulty?.confidence);
  if (score === undefined || confidence === undefined || confidence < CONFIDENCE_FLOOR) return "medium";
  return score >= HARD_SCORE ? "high" : "medium";
}

/**
 * The Sonnet route a direct subagent launch should run on, before any effort suffix.
 * A launch that names another model, carries its own suffix, or runs as a
 * workflow/management call has none: its owner already decided.
 */
export function workerBaseModel(input: any, sessionModel: string | undefined): string | undefined {
  if (!input || typeof input !== "object") return undefined;
  if (input.action || input.workflow || input.workflowScript || input.workflowScriptPath) return undefined;
  if (typeof input.agent !== "string" || typeof input.task !== "string") return undefined;
  const model: string | undefined = input.model ?? sessionModel;
  return model && !SUFFIX.test(model) && isSonnetRoute(model) ? model : undefined;
}

const CODEX_AGENTS: Record<string, string> = { "codex-exec": "codex-jev", "codex-exec-writer": "codex-jev-writer" };

/** The Jev-aware Codex agent for a direct launch of a built-in one, which cannot choose a model. */
export function redirectCodexAgent(input: any): string | undefined {
  if (!input || typeof input !== "object" || input.action || input.workflow || input.workflowScript || input.workflowScriptPath) return undefined;
  return typeof input.agent === "string" ? CODEX_AGENTS[input.agent] : undefined;
}

// ---- Imperative shell: the only code that touches env, network and Pi. ----

/** One bounded Jev call per worker launch. Any failure keeps medium; error text is never surfaced. */
export async function chooseEffort(task: string, key: string, fetchImpl: typeof fetch = fetch): Promise<"medium" | "high"> {
  try {
    const response = await fetchImpl(JEV_URL, {
      method: "POST",
      headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
      body: JSON.stringify(buildRequestBody(task)),
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) return "medium";
    return effortFromAnswers(((await response.json()) as any).answers);
  } catch {
    return "medium";
  }
}

export default function (pi: ExtensionAPI) {
  // The extension may be installed globally; only the opt-in launcher enables it.
  if (process.env.JEV_ROUTED_SESSION !== "1") return;
  // The launcher hands the key to this process only. Take it now so neither the
  // bash tool nor child sessions inherit it; children then leave launches alone.
  const jevKey = process.env.JEV_KEY_HANDOFF;
  delete process.env.JEV_KEY_HANDOFF;
  // Set by the launcher only when the codex-jev agents are installed.
  const redirectCodex = process.env.JEV_CODEX_AGENTS === "1";
  if (jevKey || redirectCodex) {
    pi.on("tool_call", async (event, ctx) => {
      if (event.toolName !== "subagent") return;
      const input = event.input as any;
      const codex = redirectCodex ? redirectCodexAgent(input) : undefined;
      if (codex) {
        input.agent = codex; // codex-jev asks Jev for the gpt-6 model and effort itself
        return;
      }
      if (!jevKey) return;
      const base = workerBaseModel(input, ctx.model ? `${ctx.model.provider}/${ctx.model.id}` : undefined);
      if (!base) return;
      const effort = await chooseEffort(input.task, jevKey);
      input.model = `${base}:${effort}`;
      if (ctx.hasUI) ctx.ui.notify(`Jev worker effort: ${effort}`, "info");
    });
  }
  const exhausted = new Set<string>();
  pi.on("agent_before_settle", async (event, ctx) => {
    if (event.outcome !== "error" || !ctx.model) return;
    const current = `${ctx.model.provider}/${ctx.model.id}`;
    if (!isSonnetRoute(current) || !hitUsageLimit(event.context.contextMessages)) return;

    exhausted.add(current);
    const available = ctx.modelRegistry.getAvailable().map((model) => `${model.provider}/${model.id}`);
    for (const [provider, modelId] of fallbackCandidates(exhausted, available)) {
      const model = ctx.modelRegistry.find(provider, modelId);
      if (!model || !(await pi.setModel(model))) continue;
      // Preserve the fixed effort chosen before the session, even across providers.
      if (ctx.thinkingLevel) pi.setThinkingLevel(ctx.thinkingLevel);
      if (ctx.hasUI) ctx.ui.notify(`Sonnet provider limit: ${current} → ${provider}/${modelId}`, "warning");
      return {
        // An error ends with an assistant message; append a context-visible
        // boundary so Pi can make a fresh request rather than dead-end.
        entries: [{ type: "custom_message" as const, customType: "jev-provider-switch", content: "The previous provider hit a usage limit. Retry the interrupted request on the new provider; do not repeat completed tool actions.", display: false }],
        continue: true,
      };
    }
    if (ctx.hasUI) ctx.ui.notify(`Sonnet provider limit: ${current}; no alternate provider available`, "error");
  });
}
