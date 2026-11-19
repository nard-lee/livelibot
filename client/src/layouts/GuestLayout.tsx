import { Outlet, type NonIndexRouteObject } from "react-router";
import { SiteHeader } from "@/components/site-header";

export default function GuestLayout() {
    return (
        <div className="flex min-h-svh flex-col bg-background">
            <SiteHeader/>
            <main className="flex flex-1 flex-col">
                <Outlet/>
            </main>
        </div>
    )
}

export const guestRoute: NonIndexRouteObject = {
    path: "/",
    Component: GuestLayout,
};
