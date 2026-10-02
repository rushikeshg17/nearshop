"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import type { Meta, User } from "@/lib/types";

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: () => api.get<User | null>("/auth/me"),
    staleTime: 5 * 60_000,
  });
}

export function useMeta() {
  return useQuery({
    queryKey: ["meta"],
    queryFn: () => api.get<Meta>("/meta"),
    staleTime: 10 * 60_000,
  });
}

export function useSignOut() {
  const qc = useQueryClient();
  const router = useRouter();
  return async () => {
    await api.post("/auth/logout").catch(() => undefined);
    qc.clear();
    qc.setQueryData(["me"], null);
    router.push("/");
    router.refresh();
  };
}

export function homeFor(user: User | null | undefined) {
  if (!user) return "/";
  if (user.role === "owner") return "/shop";
  if (user.role === "admin") return "/admin";
  return "/account";
}
