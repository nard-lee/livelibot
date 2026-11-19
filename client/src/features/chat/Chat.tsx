import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import type { RouteObject } from "react-router";
import { ArrowUpRight } from "lucide-react";
import { HTTPError } from "ky";
import { Composer } from "@/components/chat/composer";
import { MessageList } from "@/components/chat/message-list";
import type { Message, Source } from "@/components/chat/types";
import { api } from "@/lib/api";

type StreamEvent =
    | { event: "sources"; data: { sources: Source[] } }
    | { event: "token"; data: { text: string } }
    | { event: "done"; data: { reply: string; sources: Source[] } }
    | { event: "error"; data: { error: string } };

const HISTORY_LIMIT = 8;

const SUGGESTIONS = [
    "What do I need to get a business permit?",
    "How do I register my business with BIR?",
    "Who is eligible for the Kabuhayan Starter Kit?",
    "Ano ang mga serbisyo ng Negosyo Center?",
];

function parseFrame(frame: string): StreamEvent | null {
    let name = "";
    const dataLines: string[] = [];
    for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) {
            name = line.slice("event:".length).trim();
        } else if (line.startsWith("data:")) {
            dataLines.push(line.slice("data:".length).trim());
        }
    }
    if (!name || dataLines.length === 0) return null;
    try {
        return { event: name, data: JSON.parse(dataLines.join("\n")) } as StreamEvent;
    } catch {
        return null;
    }
}

async function readError(error: unknown): Promise<string> {
    if (error instanceof HTTPError) {
        try {
            const body = await error.response.json<{ error?: string }>();
            if (body.error) return body.error;
        } catch {
            // fall through
        }
    }
    return error instanceof Error
        ? error.message
        : "Couldn't reach the server. Please try again.";
}

function EmptyState({ onPick }: { onPick: (question: string) => void }) {
    return (
        <div className="flex flex-1 items-center justify-center px-2 pb-14">
            <div className="w-full max-w-lg">
                <img
                    src="/livellibot.png"
                    alt=""
                    width={44}
                    height={44}
                    className="size-11 rounded-xl"
                />
                <p className="mt-5 text-[11px] font-medium uppercase tracking-[0.16em] text-muted-foreground">
                    LiveliBot
                </p>
                <h1 className="mt-2 font-serif text-[28px] leading-[1.2] tracking-tight text-balance">
                    Ask about permits, taxes, and livelihood programs.
                </h1>
                <p className="mt-2.5 max-w-md text-[13.5px] leading-relaxed text-muted-foreground">
                    Answers come from the library and cite where they came from.
                </p>

                <ul className="mt-8 divide-y divide-border/80 border-y border-border/80">
                    {SUGGESTIONS.map((question) => (
                        <li key={question}>
                            <button
                                type="button"
                                onClick={() => onPick(question)}
                                className="group flex w-full items-baseline justify-between gap-4 py-3 text-left text-[13.5px] text-muted-foreground transition-colors hover:text-foreground"
                            >
                                <span>{question}</span>
                                <ArrowUpRight className="size-3.5 shrink-0 translate-y-0.5 text-muted-foreground/50 transition-transform group-hover:-translate-y-0 group-hover:translate-x-0.5 group-hover:text-foreground"/>
                            </button>
                        </li>
                    ))}
                </ul>
            </div>
        </div>
    );
}

export default function Chat() {
    const [draft, setDraft] = useState("");
    const [messages, setMessages] = useState<Message[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [isSending, setIsSending] = useState(false);
    const bottomRef = useRef<HTMLDivElement>(null);
    const abortRef = useRef<AbortController | null>(null);
    const messagesRef = useRef<Message[]>([]);

    useEffect(() => {
        bottomRef.current?.scrollIntoView({ block: "end" });
    }, [messages, isSending]);

    useEffect(() => () => abortRef.current?.abort(), []);

    function updateMessage(id: string, update: (message: Message) => Message) {
        setMessages((prev) =>
            prev.map((message) => (message.id === id ? update(message) : message)),
        );
    }

    async function streamAnswer(
        question: string,
        assistantId: string,
        history: { role: string; content: string }[],
    ) {
        const controller = new AbortController();
        abortRef.current = controller;

        try {
            const response = await api
                .post("chat/stream", {
                    json: { message: question, history },
                    signal: controller.signal,
                    headers: { Accept: "text/event-stream" },
                    // First bytes arrive only after retrieval + rerank; ky's 10s
                    // default would abort long answers mid-stream.
                    timeout: false,
                })
                .catch(async (failure: unknown) => {
                    throw new Error(await readError(failure));
                });

            const body = response.body;
            if (!body) throw new Error("Streaming is not supported by this browser.");

            const reader = body.getReader();
            const decoder = new TextDecoder("utf-8");
            let buffer = "";

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buffer += decoder.decode(value, { stream: true });

                let boundary = buffer.indexOf("\n\n");
                while (boundary >= 0) {
                    const event = parseFrame(buffer.slice(0, boundary));
                    buffer = buffer.slice(boundary + 2);
                    boundary = buffer.indexOf("\n\n");

                    if (!event) continue;
                    if (event.event === "token") {
                        const text = event.data.text;
                        updateMessage(assistantId, (message) => ({
                            ...message,
                            content: message.content + text,
                        }));
                    } else if (event.event === "sources") {
                        const sources = event.data.sources;
                        updateMessage(assistantId, (message) => ({ ...message, sources }));
                    } else if (event.event === "done") {
                        const { reply, sources } = event.data;
                        const finalMessages = messagesRef.current.map((message) =>
                            message.id === assistantId
                                ? { ...message, content: reply, sources }
                                : message,
                        );
                        messagesRef.current = finalMessages;
                        setMessages(finalMessages);
                    } else if (event.event === "error") {
                        throw new Error(event.data.error);
                    }
                }
            }
        } catch (failure) {
            if (controller.signal.aborted) return;
            setError(await readError(failure));

            const remaining = messagesRef.current.filter(
                (message) => message.id !== assistantId,
            );
            messagesRef.current = remaining;
            setMessages(remaining);
        } finally {
            abortRef.current = null;
            setIsSending(false);
        }
    }

    function sendMessage(raw: string) {
        const content = raw.trim();
        if (!content || isSending) return;

        const assistantId = crypto.randomUUID();
        const history = messagesRef.current
            .slice(-HISTORY_LIMIT)
            .map(({ role, content: text }) => ({ role, content: text }));

        const nextMessages: Message[] = [
            ...messagesRef.current,
            { id: crypto.randomUUID(), role: "user", content },
            { id: assistantId, role: "assistant", content: "" },
        ];

        messagesRef.current = nextMessages;
        setMessages(nextMessages);
        setDraft("");
        setError(null);
        setIsSending(true);
        void streamAnswer(content, assistantId, history);
    }

    function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        sendMessage(draft);
    }

    function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            event.currentTarget.form?.requestSubmit();
        }
    }

    return (
        <div className="flex h-full flex-col">
            <div className="no-scrollbar min-h-0 flex-1 overflow-y-auto">
                <div className="mx-auto flex min-h-full w-full max-w-3xl flex-col px-5 py-8 sm:px-6">
                    {messages.length === 0 && !isSending ? (
                        <EmptyState onPick={sendMessage}/>
                    ) : (
                        <MessageList messages={messages} isSending={isSending}/>
                    )}
                    <div ref={bottomRef}/>
                </div>
            </div>

            <div className="relative border-t border-border/70 bg-background">
                <div className="pointer-events-none absolute inset-x-0 -top-10 h-10 bg-gradient-to-t from-background to-transparent"/>
                <div className="mx-auto w-full max-w-3xl px-5 pb-4 pt-3 sm:px-6">
                    {error && (
                        <p className="mb-2 text-[13px] text-destructive" role="alert">
                            {error}
                        </p>
                    )}
                    <Composer
                        value={draft}
                        onChange={setDraft}
                        onSubmit={handleSubmit}
                        onKeyDown={handleKeyDown}
                        isSending={isSending}
                    />
                </div>
            </div>
        </div>
    );
}

export const chatRoute: RouteObject = {
    path: "chat",
    Component: Chat,
};
