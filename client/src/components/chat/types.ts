export type Source = {
    number?: number;
    title: string;
    snippet?: string;
    url?: string;
};

export type Message = {
    id?: string;
    role: "user" | "assistant";
    content: string;
    sources?: Source[];
};
