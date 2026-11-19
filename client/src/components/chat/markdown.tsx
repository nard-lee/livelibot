import ReactMarkdown, { type Components } from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";

const components: Components = {
    p: ({ children }) => <p>{children}</p>,
    ul: ({ children }) => <ul className="list-disc space-y-1.5 pl-5">{children}</ul>,
    ol: ({ children }) => <ol className="list-decimal space-y-1.5 pl-5">{children}</ol>,
    li: ({ children }) => (
        <li className="leading-relaxed [&>ol]:mt-1.5 [&>ul]:mt-1.5">{children}</li>
    ),
    strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
    em: ({ children }) => <em className="italic">{children}</em>,
    a: ({ href, children }) => (
        <a
            href={href}
            target="_blank"
            rel="noreferrer"
            className="font-medium underline underline-offset-4"
        >
            {children}
        </a>
    ),
    h1: ({ children }) => <h1 className="text-base font-semibold">{children}</h1>,
    h2: ({ children }) => <h2 className="text-sm font-semibold">{children}</h2>,
    h3: ({ children }) => <h3 className="text-sm font-semibold">{children}</h3>,
    blockquote: ({ children }) => (
        <blockquote className="border-l-2 pl-3 text-muted-foreground">{children}</blockquote>
    ),
    hr: () => <hr className="border-t"/>,
    pre: ({ children }) => (
        <pre className="overflow-x-auto rounded-lg bg-muted p-3 text-xs leading-relaxed">
            {children}
        </pre>
    ),
    code: ({ className, children }) => {
        const isBlock = className?.startsWith("language-") || String(children).includes("\n");
        if (isBlock) return <code className={className}>{children}</code>;
        return <code className="rounded bg-muted px-1 py-0.5 text-[0.85em]">{children}</code>;
    },
    table: ({ children }) => (
        <div className="overflow-x-auto">
            <table className="w-full border-collapse">{children}</table>
        </div>
    ),
    th: ({ children }) => (
        <th className="border-b px-2 py-1.5 text-left font-medium">{children}</th>
    ),
    td: ({ children }) => <td className="border-b px-2 py-1.5 align-top">{children}</td>,
};

export function Markdown({ content }: { content: string }) {
    return (
        <div className="flex flex-col gap-3 text-sm leading-relaxed">
            <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]} components={components}>
                {content}
            </ReactMarkdown>
        </div>
    );
}
