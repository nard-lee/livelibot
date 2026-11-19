import { BookOpen } from "lucide-react";
import { Link, NavLink } from "react-router";
import { ThemeToggle } from "@/components/theme-toggle";
import { cn } from "@/lib/utils";

export function SiteHeader() {
    return (
        <header className="sticky top-0 z-40 w-full border-b border-border/70 bg-background/90 backdrop-blur">
            <div className="flex h-14 w-full items-center px-4 sm:px-6">
                <Link
                    to="/chat"
                    className="flex shrink-0 items-center gap-2.5 text-[15px] font-semibold tracking-tight"
                >
                    <img
                        src="/livellibot.png"
                        alt=""
                        width={28}
                        height={28}
                        className="size-7 rounded-lg"
                    />
                    LiveliBot
                </Link>

                <div className="ml-auto flex items-center gap-1">
                    <NavLink
                        to="/documents"
                        className={({ isActive }) =>
                            cn(
                                "flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-[12.5px] transition-colors",
                                isActive
                                    ? "bg-accent text-foreground"
                                    : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                            )
                        }
                    >
                        <BookOpen className="size-3.5"/>
                        Library
                    </NavLink>
                    <ThemeToggle/>
                </div>
            </div>
        </header>
    );
}
