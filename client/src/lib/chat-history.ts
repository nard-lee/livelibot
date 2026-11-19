import type { Message } from "@/components/chat/types";

export type Conversation = {
    id: string;
    title: string;
    messages: Message[];
    updatedAt: number;
};

const STORAGE_KEY = "livellibot.conversations";
const MAX_CONVERSATIONS = 20;

const listeners = new Set<() => void>();
let conversations: Conversation[] = load();

function load(): Conversation[] {
    try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (!raw) return [];
        const parsed: unknown = JSON.parse(raw);
        if (!Array.isArray(parsed)) return [];
        return parsed.filter(
            (item): item is Conversation =>
                typeof item === "object" &&
                item !== null &&
                typeof (item as Conversation).id === "string" &&
                typeof (item as Conversation).title === "string" &&
                Array.isArray((item as Conversation).messages),
        );
    } catch {
        return [];
    }
}

function persist() {
    try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(conversations.slice(0, MAX_CONVERSATIONS)));
    } catch {
        // storage may be unavailable; the in-memory list still works
    }
    for (const listener of listeners) listener();
}

export function subscribe(listener: () => void): () => void {
    listeners.add(listener);
    return () => listeners.delete(listener);
}

export function getConversations(): Conversation[] {
    return conversations;
}

export function getConversation(id: string): Conversation | undefined {
    return conversations.find((item) => item.id === id);
}

export function upsertConversation(conversation: Conversation): void {
    conversations = [
        conversation,
        ...conversations.filter((item) => item.id !== conversation.id),
    ].slice(0, MAX_CONVERSATIONS);
    persist();
}

export function deleteConversation(id: string): void {
    conversations = conversations.filter((item) => item.id !== id);
    persist();
}
