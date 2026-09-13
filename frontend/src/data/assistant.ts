// Server-only: the Delta Basin AI assistant. Grounds the model in this app's
// own live data - the same derived summaries the dashboards already show
// (period totals, alerts, partner variance, HSE trend), not raw table dumps
// - plus the model's own general oil & gas / financial knowledge.
// Conversation is stateless server-side: the client resends the full
// message history each turn, nothing is persisted here (a reasonable v1
// scope call - see docs/fabric-environment-setup-log.md if this needs
// revisiting).
//
// Currently on Groq (free tier, OpenAI-compatible /v1/chat/completions -
// console.groq.com) as a placeholder for Anthropic, swapped in once billing
// is set up there. `callLLM()` below is the ONLY function that knows about
// the provider's wire format - swapping providers later means rewriting
// that one function, not anything else in this file or the UI.
//
// Needs GROQ_API_KEY. Deliberately fails closed and honestly, not with a
// fake in-character reply, when it's missing - see `configured: false`
// below - so a not-yet-wired-up state is never mistaken for the real thing.

import { createServerFn } from "@tanstack/react-start";
import { getDeltaBasinData } from "@/data/fabric-data";
import {
  createDeltaBasin,
  generateMockRaw,
  formatBbl,
  formatBopd,
  formatHours,
  formatPct,
  formatUsd,
} from "@/data/delta-basin";

export type ChatMessage = { role: "user" | "assistant"; content: string };

async function buildContextDigest(): Promise<string> {
  const raw = await getDeltaBasinData();
  const basin = createDeltaBasin(raw ?? generateMockRaw());
  const periodId = basin.currentPeriodId;
  const s = basin.summaryForPeriod(periodId);
  const alerts = basin.alertsForPeriod(periodId);
  const byPartner = basin.reconciliationByPartner(periodId);
  const hseTail = basin.hseTrend().slice(-3);

  const lines: string[] = [];
  lines.push(`Current reporting period: ${basin.periodLabel(periodId)} (${periodId}).`);
  lines.push("");
  lines.push("## Reconciliation");
  lines.push(
    `Allocated ${formatBbl(s.allocated)}, lifted ${formatBbl(s.lifted)}, net variance ${formatBbl(s.netVarianceBbl)} (${s.netVariancePct.toFixed(2)}%). ${s.disputedCount} disputed, ${s.pendingCount} pending cash call(s).`,
  );
  for (const p of byPartner) {
    lines.push(
      `- ${p.partner.name}: allocated ${formatBbl(p.allocatedBbl)}, lifted ${formatBbl(p.liftedBbl)}, variance ${p.variancePct.toFixed(2)}% (${p.flag}), cash call ${p.cashCallStatus} (${formatUsd(p.cashCallUsd)}).`,
    );
  }
  lines.push("");
  lines.push("## Production");
  lines.push(
    `Actual ${formatBopd(s.actual)} vs. forecast ${formatBopd(s.forecast)} (${s.forecastAttainmentPct.toFixed(1)}% attainment). ${s.wellsOnline}/${s.wellsTotal} wells online, fleet uptime ${s.uptimePct.toFixed(1)}%.`,
  );
  lines.push("");
  lines.push("## HSE");
  lines.push(`Trailing-12-month TRIR ${s.trir.toFixed(2)}, ${s.monthIncidents} recordable incident(s) this period.`);
  for (const m of hseTail) {
    lines.push(`- ${m.period}: ${m.incidents} incident(s), TRIR ${m.trir}, ${formatHours(m.hoursWorked)} worked.`);
  }
  lines.push("");
  if (alerts.length > 0) {
    lines.push("## Open alerts this period");
    for (const a of alerts) lines.push(`- [${a.level}] ${a.title} — ${a.detail}`);
  }
  return lines.join("\n");
}

const SYSTEM_PROMPT_HEADER = `You are the Delta Basin assistant, built into CUSTOMER0's upstream JV reconciliation, production, and HSE platform (a pre-discovery pilot with synthetic data - be clear about that if asked whether figures are real).

You can see the current period's data below - reconciliation variance by partner, production vs. forecast, HSE incidents/TRIR, and open alerts. Answer questions about it directly and specifically, citing real numbers from the data. You also have general knowledge of oil & gas industry economics, JV accounting, upstream operations, and financial/market context - use it to add relevant context, but be clear when you're speaking generally vs. citing this platform's own data.

Keep answers concise and concrete. If asked about something outside the provided data (e.g. a different period, a field not listed), say so rather than guessing.

Current data:
`;

/** The only function that speaks the LLM provider's wire format. Currently
 * Groq (OpenAI-compatible chat completions). Returns the reply text, or
 * throws on any failure - the caller turns that into the user-facing error
 * state. To swap to Anthropic later: read ANTHROPIC_API_KEY instead,
 * POST to https://api.anthropic.com/v1/messages with header
 * `x-api-key`/`anthropic-version` instead of `Authorization: Bearer`, move
 * `systemPrompt` to a top-level `system` field instead of a messages[0]
 * entry, and parse `body.content[0].text` instead of
 * `body.choices[0].message.content`. Nothing outside this function needs to
 * change. */
async function callLLM(systemPrompt: string, messages: ChatMessage[]): Promise<string> {
  const apiKey = process.env["GROQ_API_KEY"];
  if (!apiKey) throw new Error("not-configured");

  const resp = await fetch("https://api.groq.com/openai/v1/chat/completions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "content-type": "application/json",
    },
    body: JSON.stringify({
      model: "openai/gpt-oss-120b",
      max_tokens: 1024,
      messages: [{ role: "system", content: systemPrompt }, ...messages.map((m) => ({ role: m.role, content: m.content }))],
    }),
  });

  if (!resp.ok) {
    const errText = await resp.text();
    console.error("[assistant] Groq API error:", resp.status, errText);
    throw new Error("provider-error");
  }

  const body = (await resp.json()) as { choices?: { message?: { content?: string } }[] };
  const text = body.choices?.[0]?.message?.content;
  if (!text) throw new Error("empty-response");
  return text;
}

export const askAssistant = createServerFn({ method: "POST" })
  .validator((data: { messages: ChatMessage[] }) => data)
  .handler(async ({ data }): Promise<{ configured: boolean; reply: string | null; error: string | null }> => {
    if (!process.env["GROQ_API_KEY"]) {
      return { configured: false, reply: null, error: null };
    }

    try {
      const digest = await buildContextDigest();
      const reply = await callLLM(SYSTEM_PROMPT_HEADER + digest, data.messages);
      return { configured: true, reply, error: null };
    } catch (err) {
      console.error("[assistant] request failed:", err);
      return { configured: true, reply: null, error: "The assistant is temporarily unavailable. Please try again." };
    }
  });
