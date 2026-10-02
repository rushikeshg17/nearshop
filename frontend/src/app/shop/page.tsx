"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, Bike, ClipboardList, Info, PackageCheck, RefreshCw, Star, TrendingDown, TrendingUp } from "lucide-react";
import { AnimatePresence } from "motion/react";
import Link from "next/link";

import { Freshness, StockPill } from "@/components/common/indicators";
import { ProductThumb } from "@/components/common/product-thumb";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { PageTitle, StatTile } from "@/components/dashboard/dashboard-shell";
import { SalesChart } from "@/components/dashboard/sales-chart";
import { OwnerOrderCard, OwnerReservationCard } from "@/components/owner/queue-cards";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { formatPrice } from "@/lib/format";
import type { OwnerOverview } from "@/lib/types";

export default function OwnerOverviewPage() {
  const q = useQuery({ queryKey: ["owner", "overview"], queryFn: () => api.get<OwnerOverview>("/owner/overview"), refetchInterval: 15_000 });
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const d = q.data;
  if (!d) return <ListSkeleton rows={4} />;

  const delta = d.revenue_prev_7d ? ((d.revenue_7d - d.revenue_prev_7d) / d.revenue_prev_7d) * 100 : null;
  const needsAction = d.reservation_requests.length + d.pending_orders.length;

  return (
    <>
      <PageTitle
        title={`Good ${new Date().getHours() < 12 ? "morning" : new Date().getHours() < 17 ? "afternoon" : "evening"}`}
        description={
          <span className="inline-flex flex-wrap items-center gap-x-2">
            <Freshness at={d.inventory.updated_at} prefix="Your stock counts were updated" />
            <Link href="/shop/inventory" className="font-medium text-foreground underline underline-offset-4">Update now</Link>
          </span>
        }
        action={<Button asChild variant="outline"><Link href={`/shops/${d.shop.slug}`}>View as customer <ArrowRight /></Link></Button>}
      />

      {d.includes_demo_data && (
        <p className="mb-6 flex items-center gap-2 rounded-xl bg-info-soft px-3 py-2 text-xs text-info-ink">
          <Info className="size-3.5 shrink-0" /> Sales history includes seeded demo data so charts and forecasts have something to learn from. Real pickups and deliveries are added as they complete.
        </p>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Revenue today" value={formatPrice(d.today.revenue)} hint={`${d.today.units} units sold`} icon={TrendingUp} tone="brand" />
        <StatTile
          label="Last 7 days"
          value={formatPrice(d.revenue_7d)}
          hint={delta !== null ? <span className={delta >= 0 ? "text-success-ink" : "text-destructive"}>{delta >= 0 ? "+" : ""}{delta.toFixed(0)}% vs previous week</span> : undefined}
          icon={delta !== null && delta < 0 ? TrendingDown : TrendingUp}
        />
        <StatTile label="Pickups waiting" value={d.queue.pickups_waiting} hint={`${d.queue.reservation_requests} new requests`} icon={PackageCheck} href="/shop/reservations" />
        <StatTile label="Low or out of stock" value={d.inventory.low_stock + d.inventory.out_of_stock} hint={`of ${d.inventory.listings} listings`} icon={AlertTriangle} tone="warning" href="/shop/inventory?stock=low_stock" />
      </div>

      <div className="mt-8 grid gap-8 xl:grid-cols-[1.25fr_1fr]">
        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-lg font-semibold">
              Needs your attention
              {needsAction > 0 && <span className="grid size-6 place-items-center rounded-full bg-brand text-xs text-brand-foreground tabular">{needsAction}</span>}
            </h2>
            <Link href="/shop/reservations" className="text-sm text-muted-foreground hover:text-foreground">All reservations</Link>
          </div>
          {needsAction === 0 ? (
            <div className="rounded-2xl border border-dashed p-8 text-center">
              <ClipboardList className="mx-auto size-6 text-muted-foreground" />
              <p className="mt-2 text-sm font-medium">No new requests</p>
              <p className="text-sm text-muted-foreground">New reservations and delivery orders appear here instantly.</p>
            </div>
          ) : (
            <ul className="space-y-3">
              <AnimatePresence>
                {d.reservation_requests.map((r) => <OwnerReservationCard key={`r${r.id}`} r={r} />)}
                {d.pending_orders.map((o) => <OwnerOrderCard key={`o${o.id}`} o={o} />)}
              </AnimatePresence>
            </ul>
          )}
          {d.queue.deliveries_in_progress > 0 && (
            <Link href="/shop/orders" className="mt-3 flex items-center justify-between rounded-2xl border bg-card p-4 text-sm hover:shadow-lift">
              <span className="inline-flex items-center gap-2"><Bike className="size-4 text-brand" /> {d.queue.deliveries_in_progress} deliveries in progress</span>
              <ArrowRight className="size-4" />
            </Link>
          )}
        </section>

        <section className="rounded-2xl border bg-card p-5">
          <div className="flex items-baseline justify-between">
            <h2 className="font-semibold">Sales, last 30 days</h2>
            <p className="text-sm text-muted-foreground tabular">{formatPrice(d.revenue_30d)}</p>
          </div>
          <SalesChart data={d.sales_series} className="mt-4 h-52 w-full" />
          <div className="mt-4 flex items-center gap-2 border-t pt-4 text-sm">
            <Star className="size-4 fill-warning text-warning" />
            <span className="font-medium">{d.rating.avg?.toFixed(1) ?? "-"}</span>
            <span className="text-muted-foreground">from {d.rating.count} reviews</span>
            <Link href="/shop/reviews" className="ml-auto text-muted-foreground hover:text-foreground">Read reviews</Link>
          </div>
        </section>
      </div>

      <div className="mt-8 grid gap-8 lg:grid-cols-2">
        <section>
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-lg font-semibold">Running low</h2>
            <Link href="/shop/insights" className="text-sm text-muted-foreground hover:text-foreground">AI restock plan</Link>
          </div>
          {d.low_stock.length ? (
            <ul className="divide-y rounded-2xl border bg-card">
              {d.low_stock.map((p) => (
                <li key={p.id} className="flex items-center gap-3 p-3">
                  <ProductThumb icon={p.icon} imageUrl={p.image_url} category={p.category} alt="" size="sm" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{p.name}</p>
                    <p className="text-xs text-muted-foreground">
                      {p.days_to_stockout !== null ? `Runs out in ~${Math.max(0, Math.round(p.days_to_stockout))} days` : "No recent sales"}
                      {p.recommended_restock ? ` · restock ${p.recommended_restock}` : ""}
                    </p>
                  </div>
                  <StockPill status={p.stock_status} quantity={p.quantity} compact />
                </li>
              ))}
            </ul>
          ) : (
            <p className="rounded-2xl border border-dashed p-6 text-center text-sm text-muted-foreground">Everything is well stocked.</p>
          )}
        </section>
        <section>
          <h2 className="mb-3 text-lg font-semibold">Top sellers, 30 days</h2>
          <ul className="divide-y rounded-2xl border bg-card">
            {d.top_products.map((p, i) => (
              <li key={p.id} className="flex items-center gap-3 p-3">
                <span className="w-5 text-center text-sm text-muted-foreground tabular">{i + 1}</span>
                <ProductThumb icon={p.icon} imageUrl={p.image_url} category={p.category} alt="" size="sm" />
                <p className="min-w-0 flex-1 truncate text-sm font-medium">{p.name}</p>
                <span className="text-right text-sm tabular">
                  <span className="block font-medium">{formatPrice(p.revenue)}</span>
                  <span className="text-xs text-muted-foreground">{p.units} sold</span>
                </span>
              </li>
            ))}
            {!d.top_products.length && <li className="p-6 text-center text-sm text-muted-foreground">No sales yet.</li>}
          </ul>
        </section>
      </div>
      <p className="mt-8 flex items-center gap-1.5 text-xs text-muted-foreground"><RefreshCw className="size-3" /> Refreshes automatically every 15 seconds.</p>
    </>
  );
}
