"use client";

import { useQuery } from "@tanstack/react-query";
import { BrainCircuit, LayoutDashboard, Scale, ShieldCheck, Store, Users } from "lucide-react";
import Link from "next/link";

import { EmptyState, ListSkeleton } from "@/components/common/states";
import { DashboardShell } from "@/components/dashboard/dashboard-shell";
import { Button } from "@/components/ui/button";
import { useMe } from "@/hooks/use-session";
import { api } from "@/lib/api";
import type { AdminOverview } from "@/lib/types";

export function AdminShell({ children }: { children: React.ReactNode }) {
  const { data: me, isLoading } = useMe();
  const overview = useQuery({ queryKey: ["admin", "overview"], queryFn: () => api.get<AdminOverview>("/admin/overview"), enabled: me?.role === "admin" });
  if (isLoading) return <div className="p-10"><ListSkeleton /></div>;
  if (!me || me.role !== "admin") {
    return (
      <div className="mx-auto max-w-lg px-4 py-24">
        <EmptyState icon={ShieldCheck} title="Admins only" description="Sign in with an admin account to see platform analytics."
          action={<Button asChild><Link href="/login?next=/admin">Sign in</Link></Button>} />
      </div>
    );
  }
  const items = [
    { href: "/admin", label: "Overview", icon: LayoutDashboard, exact: true },
    { href: "/admin/anomalies", label: "Price review", icon: Scale, badge: overview.data?.totals.open_price_flags },
    { href: "/admin/shops", label: "Shops", icon: Store },
    { href: "/admin/users", label: "Users", icon: Users },
    { href: "/ai", label: "AI Lab", icon: BrainCircuit },
  ];
  return <DashboardShell title="NearShop admin" subtitle={me.email} items={items}>{children}</DashboardShell>;
}
