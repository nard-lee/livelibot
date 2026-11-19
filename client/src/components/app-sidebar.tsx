import { useSyncExternalStore } from "react";
import { useLocation, useNavigate } from "react-router";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getConversations, subscribe } from "@/lib/chat-history";
import { cn } from "@/lib/utils";

export function AppSidebar() {
    const navigate = useNavigate();
    const location = useLocation();
    const conversations = useSyncExternalStore(subscribe, getConversations);
    const activeId = new URLSearchParams(location.search).get("c");

    function startNewChat() {
        navigate(`/chat?new=${Date.now()}`);
    }

    return (
        <aside className="hidden w-60 shrink-0 flex-col border-r border-border bg-muted/30 md:flex">
            <div className="p-3">
                <Button
                    size="sm"
                    className="w-full justify-start gap-2"
                    onClick={startNewChat}
                >
                    <Plus/>
                    New chat
                </Button>
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto px-2 pb-3">
                <p className="px-2 py-1 text-[11px] text-muted-foreground">Recent</p>

                {conversations.length === 0 ? (
                    <p className="px-2 py-1 text-[12px] leading-relaxed text-muted-foreground">
                        No conversations yet.
                    </p>
                ) : (
                    <ul className="flex flex-col gap-0.5">
                        {conversations.map((conversation) => (
                            <li key={conversation.id}>
                                <button
                                    type="button"
                                    onClick={() => navigate(`/chat?c=${conversation.id}`)}
                                    className={cn(
                                        "w-full truncate rounded-md px-2 py-1.5 text-left text-[12.5px] transition-colors",
                                        conversation.id === activeId
                                            ? "bg-background text-foreground ring-1 ring-border/70"
                                            : "text-muted-foreground hover:bg-background/60 hover:text-foreground",
                                    )}
                                >
                                    {conversation.title}
                                </button>
                            </li>
                        ))}
                    </ul>
                )}
            </div>
        </aside>
    );
}
