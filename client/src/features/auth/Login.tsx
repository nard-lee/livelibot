import type { FormEvent } from "react";
import { Link, type RouteObject } from "react-router";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function Login() {
    function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault();
    }

    return (
        <div className="flex min-h-[60vh] items-center justify-center px-4 py-12">
            <Card className="w-full max-w-sm">
            <CardHeader>
                <CardTitle>Log in</CardTitle>
                <CardDescription>Welcome back. Enter your details to continue.</CardDescription>
            </CardHeader>
            <CardContent>
                <form className="grid gap-4" onSubmit={handleSubmit}>
                    <div className="grid gap-2">
                        <Label htmlFor="email">Email</Label>
                        <Input id="email" name="email" type="email" placeholder="you@example.com" autoComplete="email" required />
                    </div>
                    <div className="grid gap-2">
                        <Label htmlFor="password">Password</Label>
                        <Input id="password" name="password" type="password" autoComplete="current-password" required />
                    </div>
                    <Button type="submit" className="w-full">Log in</Button>
                </form>
            </CardContent>
            <CardFooter className="justify-center">
                <p className="text-sm text-muted-foreground">
                    Don't have an account?{" "}
                    <Link to="/signup" className="font-medium text-foreground underline-offset-4 hover:underline">
                        Sign up
                    </Link>
                </p>
            </CardFooter>
            </Card>
        </div>
    )
}

export const loginRoute: RouteObject = {
    path: "login",
    Component: Login,
};
