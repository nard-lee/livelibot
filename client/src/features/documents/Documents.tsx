import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import type { RouteObject } from "react-router";
import { HTTPError } from "ky";
import { Eye, Plus, RefreshCw, RotateCcw, Trash2, Upload, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

export type DocumentInfo = {
    name: string;
    title: string;
    chunks: number;
    bytes: number;
    modified_at: number;
};

export type UrlInfo = {
    url: string;
    title: string;
    chunks: number;
    cached: boolean;
};

export type IndexStats = {
    chunks: number;
    documents: number;
    model: string;
    dimensions: number;
    built_at: string | null;
    rerank: boolean;
    bm25: boolean;
    details: { source: string; title: string; chunks: number }[];
};

type DocumentsResponse = {
    documents: DocumentInfo[];
    urls: UrlInfo[];
    index: IndexStats;
    max_upload_bytes: number;
};

export type IndexProgress = {
    stage: string;
    detail: string;
    done: number;
    total: number;
    started: number;
    finished: number;
    elapsed: number;
    percent: number | null;
    log: { stage: string; message: string; elapsed: number }[];
};

type LastAction =
    | { kind: "upload"; file: File }
    | { kind: "url"; url: string }
    | { kind: "refresh-url"; url: string }
    | { kind: "remove-file"; name: string }
    | { kind: "remove-url"; url: string };

type PendingDelete =
    | { kind: "file"; name: string }
    | { kind: "url"; url: string };

const STAGE_LABELS: Record<string, string> = {
    idle: "Preparing",
    warming: "Warming up",
    uploading: "Reading file",
    fetching: "Fetching page",
    reading: "Reading sources",
    chunking: "Chunking",
    embedding: "Embedding",
    saving: "Saving index",
    removing: "Updating index",
    done: "Index ready",
    error: "Indexing failed",
};

const DEFAULT_MAX_UPLOAD = 10 * 1024 * 1024;

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
        : "Something went wrong. Please try again.";
}

function formatBytes(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export default function Documents() {
    const [data, setData] = useState<DocumentsResponse | null>(null);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [notice, setNotice] = useState<string | null>(null);
    const [progress, setProgress] = useState<IndexProgress | null>(null);
    const [lastAction, setLastAction] = useState<LastAction | null>(null);
    const [pendingDelete, setPendingDelete] = useState<PendingDelete | null>(null);
    const [panelHidden, setPanelHidden] = useState(false);
    const [urlDraft, setUrlDraft] = useState("");

    const urls = data?.urls ?? [];
    const fileInputRef = useRef<HTMLInputElement>(null);
    const urlInputRef = useRef<HTMLInputElement>(null);
    const logRef = useRef<HTMLDivElement>(null);
    const actionStartedAt = useRef(0);
    const logLength = progress?.log?.length ?? 0;

    const refresh = useCallback(async () => {
        try {
            setData(await api.get("documents", { timeout: 30_000 }).json<DocumentsResponse>());
        } catch (failure) {
            setError(await readError(failure));
        }
    }, []);

    useEffect(() => {
        void refresh();
    }, [refresh]);

    useEffect(() => {
        if (!busy) return;

        let cancelled = false;
        const poll = async () => {
            try {
                const next = await api
                    .get("index/progress", { timeout: 5_000 })
                    .json<IndexProgress>();
                if (cancelled) return;
                if (next.finished && next.finished < actionStartedAt.current - 0.05) return;
                setProgress(next);
            } catch {
                // best effort
            }
        };

        void poll();
        const timer = window.setInterval(poll, 400);
        return () => {
            cancelled = true;
            window.clearInterval(timer);
        };
    }, [busy]);

    useEffect(() => {
        if (!busy) return;
        const element = logRef.current;
        if (element) element.scrollTop = element.scrollHeight;
    }, [busy, logLength]);

    function markStart(action: LastAction) {
        actionStartedAt.current = Date.now() / 1000;
        setLastAction(action);
        setProgress(null);
        setPanelHidden(false);
        setError(null);
        setNotice(null);
        setBusy(true);
    }

    async function fetchProgress() {
        try {
            setProgress(
                await api.get("index/progress", { timeout: 5_000 }).json<IndexProgress>(),
            );
        } catch {
            // best effort
        }
    }

    async function upload(file: File) {
        markStart({ kind: "upload", file });
        const form = new FormData();
        form.append("file", file);
        try {
            await api.post("documents", { body: form, timeout: 300_000 });
            await refresh();
            await fetchProgress();
        } catch (failure) {
            setError(await readError(failure));
        } finally {
            setBusy(false);
        }
    }

    async function submitUrl(url: string) {
        markStart({ kind: "url", url });
        try {
            const result = await api
                .post("documents/urls", { json: { url }, timeout: 300_000 })
                .json<{ source: UrlInfo; warning: string | null }>();
            if (result.warning) {
                setNotice(`Added the page, but fetching failed: ${result.warning}`);
            }
            await refresh();
            await fetchProgress();
        } catch (failure) {
            setError(await readError(failure));
        } finally {
            setBusy(false);
        }
    }

    function handleAddUrl(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
        const url = urlDraft.trim();
        if (!url || busy) return;
        setUrlDraft("");
        void submitUrl(url);
    }

    async function refreshUrl(url: string) {
        markStart({ kind: "refresh-url", url });
        try {
            const result = await api
                .post("documents/urls/refresh", { json: { url }, timeout: 300_000 })
                .json<{ source: UrlInfo; warning: string | null }>();
            if (result.warning) {
                setNotice(`Could not fetch the page: ${result.warning}`);
            }
            await refresh();
            await fetchProgress();
        } catch (failure) {
            setError(await readError(failure));
        } finally {
            setBusy(false);
        }
    }

    async function removeUrl(url: string) {
        setPendingDelete(null);
        markStart({ kind: "remove-url", url });
        try {
            await api.delete("documents/urls", { json: { url }, timeout: 300_000 });
            await refresh();
            await fetchProgress();
        } catch (failure) {
            setError(await readError(failure));
        } finally {
            setBusy(false);
        }
    }

    async function removeFile(name: string) {
        setPendingDelete(null);
        markStart({ kind: "remove-file", name });
        try {
            await api.delete(`documents/${encodeURIComponent(name)}`, { timeout: 300_000 });
            await refresh();
            await fetchProgress();
        } catch (failure) {
            setError(await readError(failure));
        } finally {
            setBusy(false);
        }
    }

    function retry() {
        if (!lastAction) return;
        if (lastAction.kind === "upload") void upload(lastAction.file);
        else if (lastAction.kind === "url") void submitUrl(lastAction.url);
        else if (lastAction.kind === "refresh-url") void refreshUrl(lastAction.url);
        else if (lastAction.kind === "remove-file") void removeFile(lastAction.name);
        else void removeUrl(lastAction.url);
    }

    function dismiss() {
        setProgress(null);
        setPanelHidden(false);
        setError(null);
        setNotice(null);
    }

    const panelVisible = !panelHidden && progress !== null && progress.stage !== "idle";

    return (
        <div className="h-full overflow-y-auto">
            <div className="mx-auto flex w-full max-w-5xl flex-col gap-4 p-4 sm:p-5">
                <header className="flex flex-col gap-0.5">
                    <h1 className="text-sm font-semibold">Library</h1>
                    <p className="text-[12px] text-muted-foreground">
                        {data
                            ? `${data.documents.length} files · ${urls.length} pages · ${data.index.chunks} chunks`
                            : "Loading…"}
                    </p>
                </header>

                {notice && (
                    <p className="rounded-md border border-border bg-muted/40 px-3 py-2 text-[12px] text-muted-foreground">
                        {notice}
                    </p>
                )}
                {error && (
                    <div
                        className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-[12px] text-destructive"
                        role="alert"
                    >
                        <p>{error}</p>
                        <div className="mt-1.5 flex gap-2">
                            {lastAction && !busy && (
                                <Button size="xs" variant="outline" onClick={retry}>
                                    <RotateCcw/> Retry
                                </Button>
                            )}
                            <Button size="xs" variant="ghost" onClick={() => setError(null)}>
                                <X/> Dismiss
                            </Button>
                        </div>
                    </div>
                )}

                <div className="flex flex-col gap-2 rounded-md border border-border p-2.5 sm:flex-row sm:items-center">
                    <input
                        ref={fileInputRef}
                        type="file"
                        className="hidden"
                        accept=".md,.markdown,.txt,.pdf"
                        disabled={busy}
                        onChange={(event) => {
                            const file = event.target.files?.[0];
                            event.target.value = "";
                            if (file) void upload(file);
                        }}
                    />
                    <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        disabled={busy}
                        onClick={() => fileInputRef.current?.click()}
                    >
                        <Upload/> Upload file
                    </Button>
                    <span className="hidden text-[12px] text-muted-foreground sm:inline">or</span>
                    <form className="flex flex-1 items-center gap-2" onSubmit={handleAddUrl}>
                        <Input
                            ref={urlInputRef}
                            type="url"
                            value={urlDraft}
                            onChange={(event) => setUrlDraft(event.target.value)}
                            placeholder="Add a web page URL"
                            aria-label="Web page URL"
                            disabled={busy}
                            className="h-8 flex-1 text-[13px]"
                        />
                        <Button type="submit" size="sm" disabled={busy || !urlDraft.trim()}>
                            Add page
                        </Button>
                    </form>
                </div>
                <p className="-mt-2 text-[11px] text-muted-foreground">
                    .md, .txt, or .pdf up to{" "}
                    {formatBytes(data?.max_upload_bytes ?? DEFAULT_MAX_UPLOAD)} · stored in{" "}
                    <code>server/knowledge/</code>
                </p>

                {panelVisible && progress && (
                    <div className="sticky top-2 z-10 rounded-md border border-border bg-background">
                        <div className="flex items-center justify-between gap-3 border-b border-border px-3 py-1.5">
                            <span className="text-[12px] font-medium">
                                {busy
                                    ? STAGE_LABELS[progress.stage] ?? "Indexing"
                                    : progress.stage === "error"
                                      ? "Indexing failed"
                                      : "Index ready"}
                            </span>
                            <span className="text-[11px] text-muted-foreground tabular-nums">
                                {progress.percent !== null
                                    ? `${Math.round(progress.percent)}% · `
                                    : ""}
                                {progress.elapsed.toFixed(1)}s
                            </span>
                        </div>
                        <div className="px-3 py-2">
                            <p className="text-[11px] text-muted-foreground" aria-live="polite">
                                {progress.detail || "Waiting for the indexer…"}
                            </p>
                            <div
                                ref={logRef}
                                className="mt-2 max-h-44 overflow-y-auto rounded bg-muted/50 p-2 font-mono text-[10.5px] leading-relaxed"
                            >
                                {progress.log.length ? (
                                    progress.log.map((entry, index) => (
                                        <p
                                            key={`${entry.elapsed}-${index}`}
                                            className="whitespace-pre-wrap"
                                        >
                                            <span className="text-muted-foreground">
                                                [{entry.elapsed.toFixed(1)}s]
                                            </span>{" "}
                                            {entry.message}
                                        </p>
                                    ))
                                ) : (
                                    <p className="text-muted-foreground">starting…</p>
                                )}
                            </div>
                            <div className="mt-2 flex flex-wrap items-center gap-1.5">
                                {busy && (
                                    <Button
                                        size="xs"
                                        variant="ghost"
                                        onClick={() => setPanelHidden(true)}
                                    >
                                        <X/> Hide
                                    </Button>
                                )}
                                {!busy && progress.stage === "done" && (
                                    <>
                                        {lastAction?.kind === "upload" && (
                                            <Button
                                                size="xs"
                                                variant="outline"
                                                onClick={() => fileInputRef.current?.click()}
                                            >
                                                <Upload/> Upload another
                                            </Button>
                                        )}
                                        {(lastAction?.kind === "url" ||
                                            lastAction?.kind === "refresh-url") && (
                                            <Button
                                                size="xs"
                                                variant="outline"
                                                onClick={() => urlInputRef.current?.focus()}
                                            >
                                                <Plus/> Add another
                                            </Button>
                                        )}
                                        <Button size="xs" variant="ghost" onClick={dismiss}>
                                            <X/> Dismiss
                                        </Button>
                                    </>
                                )}
                                {!busy && progress.stage === "error" && (
                                    <>
                                        <Button
                                            size="xs"
                                            variant="outline"
                                            onClick={retry}
                                            disabled={!lastAction}
                                        >
                                            <RotateCcw/> Retry
                                        </Button>
                                        <Button size="xs" variant="ghost" onClick={dismiss}>
                                            <X/> Dismiss
                                        </Button>
                                    </>
                                )}
                            </div>
                        </div>
                    </div>
                )}

                {panelHidden && progress && progress.stage !== "idle" && (
                    <Button
                        type="button"
                        size="xs"
                        variant="outline"
                        className="self-start"
                        onClick={() => setPanelHidden(false)}
                    >
                        <Eye/> Show indexing log
                    </Button>
                )}

                <div className="overflow-x-auto rounded-md border border-border">
                    <table className="w-full text-left text-[13px]">
                        <thead className="border-b border-border bg-muted/40 text-[11px] text-muted-foreground">
                            <tr>
                                <th className="px-3 py-2 font-medium">Source</th>
                                <th className="px-3 py-2 font-medium">Type</th>
                                <th className="px-3 py-2 text-right font-medium">Chunks</th>
                                <th className="w-44 px-3 py-2"/>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-border">
                            {data?.documents.map((document) => (
                                <tr key={document.name}>
                                    <td className="w-full max-w-0 px-3 py-2">
                                        <p className="truncate">{document.name}</p>
                                        <p className="text-[11px] text-muted-foreground">
                                            {formatBytes(document.bytes)}
                                        </p>
                                    </td>
                                    <td className="px-3 py-2 text-[12px] text-muted-foreground">
                                        File
                                    </td>
                                    <td className="px-3 py-2 text-right tabular-nums">
                                        {document.chunks}
                                    </td>
                                    <td className="px-3 py-2">
                                        <div className="flex items-center justify-end gap-1.5">
                                            {pendingDelete?.kind === "file" &&
                                            pendingDelete.name === document.name ? (
                                                <>
                                                    <Button
                                                        size="xs"
                                                        variant="destructive"
                                                        disabled={busy}
                                                        onClick={() => void removeFile(document.name)}
                                                    >
                                                        Confirm delete
                                                    </Button>
                                                    <Button
                                                        size="xs"
                                                        variant="ghost"
                                                        onClick={() => setPendingDelete(null)}
                                                    >
                                                        Cancel
                                                    </Button>
                                                </>
                                            ) : (
                                                <Button
                                                    size="icon-xs"
                                                    variant="ghost"
                                                    aria-label={`Delete ${document.name}`}
                                                    disabled={busy}
                                                    onClick={() =>
                                                        setPendingDelete({
                                                            kind: "file",
                                                            name: document.name,
                                                        })
                                                    }
                                                >
                                                    <Trash2/>
                                                </Button>
                                            )}
                                        </div>
                                    </td>
                                </tr>
                            ))}

                            {urls.map((item) => (
                                <tr key={item.url}>
                                    <td className="w-full max-w-0 px-3 py-2">
                                        <a
                                            href={item.url}
                                            target="_blank"
                                            rel="noreferrer"
                                            className="block truncate hover:underline"
                                        >
                                            {item.title}
                                        </a>
                                        <p className="truncate text-[11px] text-muted-foreground">
                                            {item.url}
                                        </p>
                                    </td>
                                    <td className="px-3 py-2 text-[12px] text-muted-foreground">
                                        Page
                                    </td>
                                    <td className="px-3 py-2 text-right tabular-nums">
                                        {item.chunks}
                                    </td>
                                    <td className="px-3 py-2">
                                        <div className="flex items-center justify-end gap-1.5">
                                            {pendingDelete?.kind === "url" &&
                                            pendingDelete.url === item.url ? (
                                                <>
                                                    <Button
                                                        size="xs"
                                                        variant="destructive"
                                                        disabled={busy}
                                                        onClick={() => void removeUrl(item.url)}
                                                    >
                                                        Confirm delete
                                                    </Button>
                                                    <Button
                                                        size="xs"
                                                        variant="ghost"
                                                        onClick={() => setPendingDelete(null)}
                                                    >
                                                        Cancel
                                                    </Button>
                                                </>
                                            ) : (
                                                <>
                                                    <Button
                                                        size="xs"
                                                        variant="ghost"
                                                        disabled={busy}
                                                        title={
                                                            item.cached
                                                                ? "Fetch this page again"
                                                                : "Fetch this page"
                                                        }
                                                        onClick={() => void refreshUrl(item.url)}
                                                    >
                                                        <RefreshCw/>
                                                        {item.cached ? "Re-fetch" : "Fetch"}
                                                    </Button>
                                                    <Button
                                                        size="icon-xs"
                                                        variant="ghost"
                                                        aria-label={`Remove ${item.url}`}
                                                        disabled={busy}
                                                        onClick={() =>
                                                            setPendingDelete({
                                                                kind: "url",
                                                                url: item.url,
                                                            })
                                                        }
                                                    >
                                                        <Trash2/>
                                                    </Button>
                                                </>
                                            )}
                                        </div>
                                    </td>
                                </tr>
                            ))}

                            {data && data.documents.length === 0 && urls.length === 0 && (
                                <tr>
                                    <td
                                        colSpan={4}
                                        className="px-3 py-6 text-center text-[12px] text-muted-foreground"
                                    >
                                        No sources yet. Upload a file or add a page above.
                                    </td>
                                </tr>
                            )}
                        </tbody>
                    </table>
                </div>

                {data && (
                    <p className="text-[11px] text-muted-foreground">
                        Index built {data.index.built_at ?? "unknown"} · {data.index.model} ·{" "}
                        {data.index.dimensions}d
                    </p>
                )}
            </div>
        </div>
    );
}

export const documentsRoute: RouteObject = {
    path: "documents",
    Component: Documents,
};
