"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, Loader2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { homeFor } from "@/hooks/use-session";
import { api, errorMessage } from "@/lib/api";
import type { User } from "@/lib/types";

const DEMO = [
  { label: "Customer", email: "priya@nearshop.demo" },
  { label: "Shop owner", email: "owner@nearshop.demo" },
  { label: "Admin", email: "admin@nearshop.demo" },
];

export function safeNext(next: string | null) {
  // Only allow same-site relative paths to avoid open redirects.
  return next && next.startsWith("/") && !next.startsWith("//") ? next : null;
}

export function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const qc = useQueryClient();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);

  const login = useMutation({
    mutationFn: () => api.post<User>("/auth/login", { email, password }),
    meta: { silent: true },
    onSuccess: (user) => {
      qc.setQueryData(["me"], user);
      qc.invalidateQueries({ refetchType: "none" });
      const next = safeNext(params.get("next"));
      const allowed = next && !(next.startsWith("/shop") && user.role !== "owner") && !(next.startsWith("/admin") && user.role !== "admin");
      router.replace(allowed ? next : homeFor(user));
    },
  });

  return (
    <div>
      <h1 className="text-3xl font-semibold">Welcome back</h1>
      <p className="mt-2 text-sm text-muted-foreground">Sign in to reserve items and track your pickups.</p>

      <form
        className="mt-8 space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          login.mutate();
        }}
      >
        <div className="space-y-1.5">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} className="h-11" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="password">Password</Label>
          <div className="relative">
            <Input
              id="password"
              type={show ? "text" : "password"}
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="h-11 pr-11"
            />
            <button
              type="button"
              onClick={() => setShow((v) => !v)}
              className="absolute top-1/2 right-2 grid size-8 -translate-y-1/2 place-items-center rounded-md text-muted-foreground hover:bg-muted"
              aria-label={show ? "Hide password" : "Show password"}
            >
              {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </div>
        </div>
        {login.isError && (
          <p role="alert" className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {errorMessage(login.error)}
          </p>
        )}
        <Button type="submit" size="lg" className="h-11 w-full" disabled={login.isPending}>
          {login.isPending && <Loader2 className="animate-spin" />} Sign in
        </Button>
      </form>

      <p className="mt-6 text-sm text-muted-foreground">
        New here?{" "}
        <Link href={`/register${params.get("next") ? `?next=${encodeURIComponent(params.get("next")!)}` : ""}`} className="font-medium text-foreground underline underline-offset-4">
          Create an account
        </Link>{" "}
        or{" "}
        <Link href="/register/shop" className="font-medium text-foreground underline underline-offset-4">list your shop</Link>
      </p>

      <div className="mt-10 rounded-2xl border border-dashed p-4">
        <p className="text-xs font-medium text-muted-foreground">Demo accounts (password in backend/.env.example)</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {DEMO.map((d) => (
            <button
              key={d.email}
              type="button"
              onClick={() => setEmail(d.email)}
              className="rounded-full border bg-card px-3 py-1 text-xs transition-colors hover:bg-accent"
            >
              {d.label}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
