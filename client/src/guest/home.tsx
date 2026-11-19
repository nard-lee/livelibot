import { redirect, type RouteObject } from "react-router";

export const homeRoute: RouteObject = {
    index: true,
    loader: () => redirect("/chat"),
};
