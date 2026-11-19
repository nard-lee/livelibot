import { Outlet, type NonIndexRouteObject } from "react-router";
import { SiteHeader } from "@/components/site-header";

export default function AuthLayout() {
    return (
        <div className="flex h-svh flex-col bg-background">
            <SiteHeader/>
            <main className="min-h-0 flex-1 overflow-hidden">
                <Outlet/>
            </main>
        </div>
    )
}

export const authRoute: NonIndexRouteObject = {
    Component: AuthLayout,
};
