// dotfiles-managed: jev-sonnet-fallback
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

// Keep subscription providers ahead of the metered route. Pi's registry only
// exposes authenticated models, so a newly authenticated Cursor joins the pool.
export const ROUTES = [
  ["github-copilot", "claude-sonnet-5.5"],
  ["cursor", "claude-sonnet-5-5"],
  ["openrouter", "anthropic/claude-sonnet-5.5"],
] as const;

export function isUsageLimit(message: string): boolean {
  return /(?:\b429\b|rate.?limit|usage.?limit|quota.?exceed|resource.?exhaust|too many requests)/i.test(message);
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

/** Compose Jev's typed answers into an effort; anything unusable means medium. */
export function effortFromAnswers(answers: any): "medium" | "high" {
  const noul = num(answers?.strict_structure?.noul);
  if (noul !== undefined && noul >= STRICT_STRUCTURE) return "high";
  const score = num(answers?.difficulty?.score);
  const confidence = num(answers?.difficulty?.confidence);
  if (score === undefined || confidence === undefined || confidence < CONFIDENCE_FLOOR) return "medium";
  return score >= HARD_SCORE ? "high" : "medium";
}

/** One bounded Jev call per worker launch. Any failure keeps medium; error text is never surfaced. */
export async function chooseEffort(task: string, key: string, fetchImpl: typeof fetch = fetch): Promise<"medium" | "high"> {
  try {
    const response = await fetchImpl(JEV_URL, {
      method: "POST",
      headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
      body: JSON.stringify({ model: "jev-latest", state: task.slice(0, 8000), questions: QUESTIONS }),
      signal: AbortSignal.timeout(5000),
    });
    if (!response.ok) return "medium";
    return effortFromAnswers(((await response.json()) as any).answers);
  } catch {
    return "medium";
  }
}

/**
 * Pin the effort on one direct subagent launch. A launch that names another model,
 * carries its own suffix, or runs as a workflow/management call is left to its owner.
 */
export function applyWorkerEffort(input: any, effort: string, sessionModel: string | undefined): boolean {
  if (!input || typeof input !== "object") return false;
  if (input.action || input.workflow || input.workflowScript || input.workflowScriptPath) return false;
  if (typeof input.agent !== "string" || typeof input.task !== "string") return false;
  const model: string | undefined = input.model ?? sessionModel;
  if (!model || SUFFIX.test(model) || !isSonnetRoute(model)) return false;
  input.model = `${model}:${effort}`;
  return true;
}

export default function (pi: ExtensionAPI) {
  // The extension may be installed globally; only the opt-in launcher enables it.
  if (process.env.JEV_ROUTED_SESSION !== "1") return;
  // The launcher hands the key to this process only. Take it now so neither the
  // bash tool nor child sessions inherit it; children then leave launches alone.
  const jevKey = process.env.JEV_KEY_HANDOFF;
  delete process.env.JEV_KEY_HANDOFF;
  if (jevKey) {
    pi.on("tool_call", async (event, ctx) => {
      if (event.toolName !== "subagent") return;
      const input = event.input as any;
      const sessionModel = ctx.model ? `${ctx.model.provider}/${ctx.model.id}` : undefined;
      // Cheap shape check first so unrelated calls never reach Jev.
      if (!applyWorkerEffort({ ...input }, "medium", sessionModel)) return;
      const effort = await chooseEffort(input.task, jevKey);
      applyWorkerEffort(input, effort, sessionModel);
      if (ctx.hasUI) ctx.ui.notify(`Jev worker effort: ${effort}`, "info");
    });
  }
  const exhausted = new Set<string>();
  pi.on("agent_before_settle", async (event, ctx) => {
    if (event.outcome !== "error" || !ctx.model) return;
    const current = `${ctx.model.provider}/${ctx.model.id}`;
    if (!ROUTES.some(([provider, model]) => `${provider}/${model}` === current)) return;
    const last = [...event.context.contextMessages].reverse().find((msg) => msg.role === "assistant");
    if (!last || last.role !== "assistant" || last.stopReason !== "error" || !isUsageLimit(last.errorMessage ?? "")) return;

    exhausted.add(current);
    for (const [provider, modelId] of ROUTES) {
      const id = `${provider}/${modelId}`;
      if (exhausted.has(id)) continue;
      const model = ctx.modelRegistry.find(provider, modelId);
      if (!model || !ctx.modelRegistry.getAvailable().some((available) => available.provider === provider && available.id === modelId)) continue;
      if (!(await pi.setModel(model))) continue;
      // Preserve the fixed effort chosen before the session, even across providers.
      if (ctx.thinkingLevel) pi.setThinkingLevel(ctx.thinkingLevel);
      if (ctx.hasUI) ctx.ui.notify(`Sonnet provider limit: ${current} → ${id}`, "warning");
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
