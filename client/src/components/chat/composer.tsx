import type { FormEvent, KeyboardEvent } from "react";
import { ArrowUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

type ComposerProps = {
    value: string;
    onChange: (value: string) => void;
    onSubmit: (event: FormEvent<HTMLFormElement>) => void;
    onKeyDown: (event: KeyboardEvent<HTMLTextAreaElement>) => void;
    isSending: boolean;
};

export function Composer({ value, onChange, onSubmit, onKeyDown, isSending }: ComposerProps) {
    return (
        <form onSubmit={onSubmit} className="flex flex-col gap-2">
            <div className="flex items-end gap-2 rounded-xl border border-border bg-card p-2 shadow-sm transition-[border-color,box-shadow] focus-within:border-primary/50 focus-within:shadow-md">
                <Textarea
                    name="message"
                    value={value}
                    onChange={(event) => onChange(event.target.value)}
                    onKeyDown={onKeyDown}
                    placeholder="Ask about permits, BIR, or livelihood programs…"
                    aria-label="Message"
                    rows={1}
                    className="max-h-40 min-h-9 flex-1 resize-none border-0 bg-transparent px-2 py-1.5 text-[14px] leading-relaxed focus-visible:ring-0 dark:bg-transparent"
                />
                <Button
                    type="submit"
                    size="icon-sm"
                    aria-label="Send"
                    disabled={!value.trim() || isSending}
                    className="shrink-0 rounded-lg"
                >
                    <ArrowUp/>
                </Button>
            </div>
            <p className="px-1 text-[11px] text-muted-foreground">
                Enter to send · Shift+Enter for a new line
            </p>
        </form>
    );
}
