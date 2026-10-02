"use client";

import { useQuery } from "@tanstack/react-query";
import { BrainCircuit, ClipboardList, FileSpreadsheet, LayoutDashboard, Library, Package, Settings, Star, Truck } from "lucide-react";
import Link from "next/link";

import { DashboardShell } from "@/components/dashboard/dashboard-shell";
import { EmptyState, ListSkeleton } from "@/components/common/states";
import { Button } from "@/components/ui/button";
import { useMe } from "@/hooks/use-session";
import { api } from "@/lib/api";
import type { OwnerOverview } from "@/lib/types";

export function OwnerShell({ children }: { children: React.ReactNode }) {
  const { data: me, isLoading } = useMe();
  const overview = useQuery({
    queryKey: ["owner", "overview"],
    queryFn: () => api.get<OwnerOverview>("/owner/overview"),
    enabled: me?.role === "owner",
    refetchInterval: 15_000,
  });

  if (isLoading) return <div className="p-10"><ListSkeleton /></div>;
  if (!me || me.role !== "owner") {
    return (
      <div className="mx-auto max-w-lg px-4 py-24">
        <EmptyState icon={Package} title="The shop dashboard is for shop owners" description="Sign in with a shop owner account, or list your shop in a few minutes."
          action={<><Button asChild><Link href="/register/shop">List your shop</Link></Button><Button asChild variant="outline"><Link href="/login?next=/shop">Sign in</Link></Button></>} />
      </div>
    );
  }

  const q = overview.data?.queue;
  const items = [
    { href: "/shop", label: "Overview", icon: LayoutDashboard, exact: true },
    { href: "/shop/reservations", label: "Reservations", icon: ClipboardList, badge: q?.reservation_requests },
    { href: "/shop/orders", label: "Delivery orders", icon: Truck, badge: q?.orders_pending },
    { href: "/shop/inventory", label: "Inventory", icon: Package },
    { href: "/shop/import", label: "Import from Excel", icon: FileSpreadsheet },
    { href: "/shop/catalog", label: "Add from catalogue", icon: Library },
    { href: "/shop/insights", label: "AI insights", icon: BrainCircuit },
    { href: "/shop/reviews", label: "Reviews", icon: Star },
    { href: "/shop/settings", label: "Shop settings", icon: Settings },
  ];
  return (
    <DashboardShell title={me.shop?.name ?? "Your shop"} subtitle={me.name} items={items} publicHref={me.shop ? `/shops/${me.shop.slug}` : undefined}>
      {children}
    </DashboardShell>
  );
}
