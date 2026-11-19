import { ChevronRight } from "lucide-react";
import { CopyButton } from "@/components/chat/copy-button";
import { Markdown } from "@/components/chat/markdown";
import type { Message } from "@/components/chat/types";

type MessageListProps = {
    messages: Message[];
    isSending: boolean;
};

const SNIPPET_LIMIT = 110;

function sourceDomain(url?: string): string | null {
    if (!url) return null;
    try {
        return new URL(url).hostname.replace(/^www\./, "");
    } catch {
        return null;
    }
}

function cleanSnippet(raw?: string): string | null {
    let text = (raw ?? "").replace(/\s+/g, " ").trim();
    if (!text) return null;

    // A fragment that opens mid-sentence ("and (3) the duty…") reads as noise.
    if (/^[a-z,;:)\]]/.test(text)) {
        const boundary = text.search(/[.!?]\s+[A-Z0-9"'“(\[]/);
        if (boundary >= 0) text = text.slice(boundary + 1).trim();
    }

    if (text.length > SNIPPET_LIMIT) {
        const cut = text.lastIndexOf(" ", SNIPPET_LIMIT);
        text = text.slice(0, cut > 40 ? cut : SNIPPET_LIMIT).trim();
    }
    return `${text.replace(/[…\s]+$/, "")}…`;
}

export function MessageList({ messages, isSending }: MessageListProps) {
    if (messages.length === 0) {
        return null;
    }

    return (
        <ul className="flex flex-col gap-7">
            {messages.map((message, index) => (
                <li key={message.id ?? index}>
                    {message.role === "user" ? (
                        <div className="flex justify-end">
                            <p className="max-w-[85%] rounded-2xl bg-secondary px-4 py-2.5 text-[14px] leading-relaxed whitespace-pre-wrap text-secondary-foreground">
                                {message.content}
                            </p>
                        </div>
                    ) : (
                        <article>
                            <div className="flex items-center justify-between gap-3">
                                <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-muted-foreground">
                                    LiveliBot
                                </span>
                                {message.content && <CopyButton text={message.content}/>}
                            </div>

                            <div className="mt-2">
                                {!message.content && isSending ? (
                                    <p className="animate-pulse text-[13px] text-muted-foreground">
                                        Searching the library…
                                    </p>
                                ) : (
                                    <Markdown content={message.content}/>
                                )}
                            </div>

                            {message.sources && message.sources.length > 0 && (
                                <details className="mt-4 rounded-lg border border-border/70 bg-muted/30 [&[open]>summary>svg]:rotate-90">
                                    <summary className="flex cursor-pointer list-none items-center gap-1.5 px-3.5 py-2.5 text-[10.5px] font-medium uppercase tracking-[0.14em] text-muted-foreground transition-colors hover:text-foreground [&::-webkit-details-marker]:hidden">
                                        <ChevronRight className="size-3 transition-transform"/>
                                        Sources ({message.sources.length})
                                    </summary>

                                    <ul className="flex flex-col gap-2.5 border-t border-border/60 px-3.5 py-3">
                                        {message.sources.map((source, sourceIndex) => {
                                            const domain = sourceDomain(source.url);
                                            const snippet = cleanSnippet(source.snippet);
                                            return (
                                                <li key={sourceIndex} className="min-w-0 text-[12.5px] leading-snug">
                                                    <div className="flex min-w-0 items-baseline gap-1.5">
                                                        <span className="shrink-0 text-muted-foreground tabular-nums">
                                                            {source.number ?? sourceIndex + 1}.
                                                        </span>
                                                        <div className="flex min-w-0 items-baseline gap-1.5">
                                                            {source.url ? (
                                                                <a
                                                                    href={source.url}
                                                                    target="_blank"
                                                                    rel="noreferrer"
                                                                    className="min-w-0 truncate font-medium underline-offset-4 hover:underline"
                                                                >
                                                                    {source.title}
                                                                </a>
                                                            ) : (
                                                                <span className="min-w-0 truncate font-medium">
                                                                    {source.title}
                                                                </span>
                                                            )}
                                                            {domain && (
                                                                <span className="shrink-0 text-[11px] text-muted-foreground">
                                                                    {domain}
                                                                </span>
                                                            )}
                                                        </div>
                                                    </div>
                                                    {snippet && (
                                                        <p className="mt-0.5 truncate pl-[1.1rem] text-[11.5px] text-muted-foreground">
                                                            {snippet}
                                                        </p>
                                                    )}
                                                </li>
                                            );
                                        })}
                                    </ul>
                                </details>
                            )}
                        </article>
                    )}
                </li>
            ))}
        </ul>
    );
}
