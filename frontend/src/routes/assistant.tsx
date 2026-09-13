import { createFileRoute } from "@tanstack/react-router";
import { useRef, useState, type FormEvent } from "react";
import { Send, Sparkles } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { PageHeader, Panel, NewBadge } from "@/components/ui-kit";
import { askAssistant, type ChatMessage } from "@/data/assistant";

/** Renders the assistant's markdown reply (bold, lists, tables) instead of
 * dumping raw `**`/`|` syntax into the chat bubble. User messages stay plain
 * text - only the model's own formatting needs interpreting. */
function AssistantReply({ content }: { content: string }) {
  return (
    <div className="space-y-2 text-sm leading-relaxed [&_a]:text-primary [&_a]:underline">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p className="leading-relaxed">{children}</p>,
          strong: ({ children }) => <strong className="font-semibold text-foreground">{children}</strong>,
          ul: ({ children }) => <ul className="ml-4 list-disc space-y-1">{children}</ul>,
          ol: ({ children }) => <ol className="ml-4 list-decimal space-y-1">{children}</ol>,
          li: ({ children }) => <li className="leading-relaxed">{children}</li>,
          h1: ({ children }) => <h3 className="mt-2 font-display text-sm font-semibold text-foreground">{children}</h3>,
          h2: ({ children }) => <h3 className="mt-2 font-display text-sm font-semibold text-foreground">{children}</h3>,
          h3: ({ children }) => <h4 className="mt-2 text-sm font-semibold text-foreground">{children}</h4>,
          code: ({ children }) => (
            <code className="rounded bg-surface-2 px-1 py-0.5 font-mono text-xs">{children}</code>
          ),
          table: ({ children }) => (
            <div className="my-2 overflow-x-auto rounded-md border border-border">
              <table className="w-full border-collapse text-xs">{children}</table>
            </div>
          ),
          thead: ({ children }) => <thead className="bg-surface-2">{children}</thead>,
          th: ({ children }) => (
            <th className="border-b border-border px-2 py-1.5 text-left text-[10px] uppercase tracking-[0.08em] text-muted-foreground">
              {children}
            </th>
          ),
          td: ({ children }) => <td className="border-b border-border px-2 py-1.5 align-top">{children}</td>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

export const Route = createFileRoute("/assistant")({
  head: () => ({
    meta: [
      { title: "Assistant — Delta Basin" },
      {
        name: "description",
        content: "Ask the Delta Basin assistant about reconciliation, production, and HSE data, or general oil & gas context.",
      },
    ],
  }),
  component: AssistantPage,
});

const SUGGESTIONS = [
  "Which partner has the largest reconciliation variance this period?",
  "How is fleet uptime trending and what's driving it?",
  "Summarize this period's HSE performance.",
  "What's a typical JV cash-call dispute resolution process?",
];

function AssistantPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [notConfigured, setNotConfigured] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement>(null);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || sending) return;
    setError(null);
    const next = [...messages, { role: "user" as const, content: trimmed }];
    setMessages(next);
    setInput("");
    setSending(true);
    try {
      const result = await askAssistant({ data: { messages: next } });
      if (!result.configured) {
        setNotConfigured(true);
        return;
      }
      if (result.error || !result.reply) {
        setError(result.error ?? "The assistant didn't return a response.");
        return;
      }
      setMessages([...next, { role: "assistant", content: result.reply }]);
    } catch {
      setError("Something went wrong reaching the assistant. Please try again.");
    } finally {
      setSending(false);
      requestAnimationFrame(() => {
        listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: "smooth" });
      });
    }
  }

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void send(input);
  }

  return (
    <>
      <PageHeader
        eyebrow="Assistant"
        title="Ask Delta Basin"
        description="Grounded in this period's reconciliation, production, and HSE data, plus general oil & gas and financial context."
        actions={<NewBadge />}
      />

      <Panel title="Delta Basin assistant" className="flex flex-col">
        {notConfigured ? (
          <div className="rounded-md border border-warning/40 bg-warning/10 p-4 text-sm text-warning">
            The assistant isn't connected yet — its LLM API key hasn't been configured for this
            environment. This is expected during development; nothing is broken.
          </div>
        ) : (
          <>
            <div ref={listRef} className="flex max-h-[50vh] min-h-[200px] flex-col gap-3 overflow-y-auto pr-1">
              {messages.length === 0 ? (
                <div className="flex flex-1 flex-col items-center justify-center gap-3 py-10 text-center">
                  <Sparkles className="size-6 text-muted-foreground" aria-hidden />
                  <p className="text-sm text-muted-foreground">
                    Ask about this period's data, or general oil &amp; gas / financial questions.
                  </p>
                  <div className="mt-2 flex flex-wrap justify-center gap-2">
                    {SUGGESTIONS.map((s) => (
                      <button
                        key={s}
                        type="button"
                        onClick={() => void send(s)}
                        className="rounded-full border border-border bg-surface px-3 py-1.5 text-xs text-foreground transition-colors hover:bg-surface-2"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                messages.map((m, i) => (
                  <div
                    key={i}
                    className={`max-w-[85%] rounded-lg px-3 py-2 text-sm leading-relaxed ${
                      m.role === "user"
                        ? "ml-auto bg-primary text-primary-foreground"
                        : "mr-auto border border-border bg-surface text-foreground"
                    }`}
                  >
                    {m.role === "assistant" ? <AssistantReply content={m.content} /> : m.content}
                  </div>
                ))
              )}
              {sending ? (
                <div className="mr-auto rounded-lg border border-border bg-surface px-3 py-2 text-sm text-muted-foreground">
                  Thinking…
                </div>
              ) : null}
            </div>

            {error ? <p className="mt-3 text-xs text-critical">{error}</p> : null}

            <form onSubmit={onSubmit} className="mt-4 flex gap-2 border-t border-border pt-4">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask a question…"
                aria-label="Ask the assistant"
                className="flex-1 rounded-md border border-border bg-surface px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:border-primary"
              />
              <button
                type="submit"
                disabled={sending || !input.trim()}
                className="flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-semibold text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Send className="size-4" aria-hidden />
                Send
              </button>
            </form>
          </>
        )}
      </Panel>
    </>
  );
}
