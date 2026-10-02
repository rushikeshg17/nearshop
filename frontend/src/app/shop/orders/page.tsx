"use client";

import { useQuery } from "@tanstack/react-query";
import { Bike } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status";
import { PageTitle } from "@/components/dashboard/dashboard-shell";
import { OwnerOrderCard } from "@/components/owner/queue-cards";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { formatDateTime, formatPrice } from "@/lib/format";
import type { Order, OwnerOverview } from "@/lib/types";

export default function OwnerOrdersPage() {
  const [scope, setScope] = useState<"active" | "history">("active");
  const overview = useQuery({ queryKey: ["owner", "overview"], queryFn: () => api.get<OwnerOverview>("/owner/overview") });
  const q = useQuery({
    queryKey: ["owner", "orders", scope],
    queryFn: () => api.get<Order[]>("/owner/orders", { scope }),
    refetchInterval: scope === "active" ? 10_000 : false,
  });

  if (overview.data && !overview.data.shop.offers_delivery && scope === "active" && !q.data?.length) {
    return (
      <>
        <PageTitle title="Delivery orders" />
        <EmptyState icon={Bike} title="You offer pickup only" description="Turn on delivery in settings to accept delivery orders. You set the radius and fee; you or your staff deliver, and customers pay cash."
          action={<Button asChild><Link href="/shop/settings">Set up delivery</Link></Button>} />
      </>
    );
  }

  return (
    <>
      <PageTitle
        title="Delivery orders"
        description="You deliver with your own staff. Customers pay cash on delivery."
        action={
          <Tabs value={scope} onValueChange={(v) => setScope(v as "active" | "history")}>
            <TabsList>
              <TabsTrigger value="active">Active</TabsTrigger>
              <TabsTrigger value="history">History</TabsTrigger>
            </TabsList>
          </Tabs>
        }
      />
      {q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : !q.data ? (
        <ListSkeleton />
      ) : scope === "active" ? (
        q.data.length ? (
          <ul className="grid gap-4 lg:grid-cols-2">{q.data.map((o) => <OwnerOrderCard key={o.id} o={o} />)}</ul>
        ) : (
          <EmptyState icon={Bike} title="No active deliveries" description="New delivery orders appear here with the customer's address and route." />
        )
      ) : (
        <div className="overflow-hidden rounded-2xl border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Code</TableHead>
                <TableHead>Items</TableHead>
                <TableHead className="hidden md:table-cell">Customer</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Total</TableHead>
                <TableHead className="hidden lg:table-cell">When</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {q.data.map((o) => (
                <TableRow key={o.id}>
                  <TableCell className="font-mono text-xs">{o.code}</TableCell>
                  <TableCell className="max-w-56 truncate">{o.items.map((i) => i.name).join(", ")}</TableCell>
                  <TableCell className="hidden md:table-cell">{o.customer?.name}</TableCell>
                  <TableCell><StatusBadge status={o.status} kind="order" /></TableCell>
                  <TableCell className="text-right tabular">{formatPrice(o.total)}</TableCell>
                  <TableCell className="hidden text-muted-foreground lg:table-cell">{formatDateTime(o.delivered_at ?? o.closed_at ?? o.created_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </>
  );
}
