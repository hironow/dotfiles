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

export default function (pi: ExtensionAPI) {
  // The extension may be installed globally; only the opt-in launcher enables it.
  if (process.env.JEV_ROUTED_SESSION !== "1") return;
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
