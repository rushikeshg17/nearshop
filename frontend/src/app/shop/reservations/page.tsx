"use client";

import { useQuery } from "@tanstack/react-query";
import { ClipboardList } from "lucide-react";
import { AnimatePresence } from "motion/react";
import { useState } from "react";

import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status";
import { PageTitle } from "@/components/dashboard/dashboard-shell";
import { OwnerReservationCard } from "@/components/owner/queue-cards";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { formatDateTime, formatPrice } from "@/lib/format";
import type { Reservation } from "@/lib/types";

const COLUMNS = [
  { status: "REQUESTED", title: "New requests", hint: "Check the shelf, then confirm or decline" },
  { status: "CONFIRMED", title: "Held for customer", hint: "Set aside. Mark ready when packed." },
  { status: "READY_FOR_PICKUP", title: "Ready at counter", hint: "Complete when they pay and collect" },
];

export default function OwnerReservationsPage() {
  const [scope, setScope] = useState<"active" | "history">("active");
  const q = useQuery({
    queryKey: ["owner", "reservations", scope],
    queryFn: () => api.get<Reservation[]>("/owner/reservations", { scope }),
    refetchInterval: scope === "active" ? 10_000 : false,
  });

  return (
    <>
      <PageTitle
        title="Reservations"
        description="Customers reserve, you confirm, they pick up and pay at the counter."
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
        q.data.length === 0 ? (
          <EmptyState icon={ClipboardList} title="No active reservations" description="When a customer reserves something from your shop it appears here, and you get a notification." />
        ) : (
          <div className="grid gap-6 xl:grid-cols-3">
            {COLUMNS.map((c) => {
              const rows = q.data.filter((r) => r.status === c.status);
              return (
                <section key={c.status}>
                  <h2 className="flex items-center gap-2 font-semibold">
                    {c.title} <span className="rounded-full bg-muted px-2 text-xs tabular">{rows.length}</span>
                  </h2>
                  <p className="mb-3 text-xs text-muted-foreground">{c.hint}</p>
                  <ul className="space-y-3">
                    <AnimatePresence>{rows.map((r) => <OwnerReservationCard key={r.id} r={r} />)}</AnimatePresence>
                    {!rows.length && <li className="rounded-2xl border border-dashed p-6 text-center text-sm text-muted-foreground">Nothing here</li>}
                  </ul>
                </section>
              );
            })}
          </div>
        )
      ) : (
        <div className="overflow-hidden rounded-2xl border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Code</TableHead>
                <TableHead>Item</TableHead>
                <TableHead className="hidden md:table-cell">Customer</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Total</TableHead>
                <TableHead className="hidden lg:table-cell">Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {q.data.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="font-mono text-xs">{r.code}</TableCell>
                  <TableCell className="max-w-56 truncate">{r.quantity} x {r.product.name}</TableCell>
                  <TableCell className="hidden md:table-cell">{r.customer?.name}</TableCell>
                  <TableCell><StatusBadge status={r.status} kind="reservation" /></TableCell>
                  <TableCell className="text-right tabular">{formatPrice(r.total)}</TableCell>
                  <TableCell className="hidden text-muted-foreground lg:table-cell">{formatDateTime(r.closed_at ?? r.completed_at ?? r.created_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </>
  );
}
