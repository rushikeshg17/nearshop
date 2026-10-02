"use client";

import { useQuery } from "@tanstack/react-query";
import { ClipboardList, IndianRupee, Info, Package, Scale, Search, Store, Users } from "lucide-react";
import Link from "next/link";
import { Bar, BarChart, CartesianGrid, XAxis } from "recharts";

import { ErrorState, ListSkeleton } from "@/components/common/states";
import { RESERVATION_LABELS, ORDER_LABELS } from "@/components/common/status";
import { PageTitle, StatTile } from "@/components/dashboard/dashboard-shell";
import { SalesChart } from "@/components/dashboard/sales-chart";
import { type ChartConfig, ChartContainer, ChartLegend, ChartLegendContent, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { api } from "@/lib/api";
import { formatCompactPrice, formatNumber, formatPrice } from "@/lib/format";
import type { AdminOverview } from "@/lib/types";

const activityConfig = {
  searches: { label: "Searches", color: "var(--chart-2)" },
  inventory_updates: { label: "Stock updates", color: "var(--chart-1)" },
} satisfies ChartConfig;

function StatusBars({ data, labels }: { data: Record<string, number>; labels: Record<string, { label: string }> }) {
  const total = Object.values(data).reduce((a, b) => a + b, 0) || 1;
  return (
    <ul className="space-y-2">
      {Object.entries(data).sort((a, b) => b[1] - a[1]).map(([k, v]) => (
        <li key={k} className="text-sm">
          <div className="flex justify-between"><span>{labels[k]?.label ?? k}</span><span className="text-muted-foreground tabular">{formatNumber(v)}</span></div>
          <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-chart-1" style={{ width: `${(v / total) * 100}%` }} /></div>
        </li>
      ))}
    </ul>
  );
}

export default function AdminOverviewPage() {
  const q = useQuery({ queryKey: ["admin", "overview"], queryFn: () => api.get<AdminOverview>("/admin/overview") });
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const d = q.data;
  if (!d) return <ListSkeleton rows={5} />;
  const t = d.totals;
  const activity = d.activity.map((a) => ({ ...a, label: new Date(`${a.date}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" }) }));
  const maxCat = Math.max(...d.categories.map((c) => c.revenue_30d), 1);

  return (
    <>
      <PageTitle title="Platform overview" description="Everything happening across NearShop." />
      <p className="mb-6 flex items-center gap-2 rounded-xl bg-info-soft px-3 py-2 text-xs text-info-ink">
        <Info className="size-3.5 shrink-0" /> 30-day revenue {formatPrice(t.revenue_30d)}, of which {formatPrice(t.revenue_30d_real)} is from real transactions. The rest is seeded demo history.
      </p>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Customers" value={formatNumber(t.customers)} icon={Users} />
        <StatTile label="Shops" value={formatNumber(t.shops)} hint={`${t.shops_verified} verified`} icon={Store} href="/admin/shops" />
        <StatTile label="Listings" value={formatNumber(t.listings)} hint={`${formatNumber(t.in_stock)} in stock`} icon={Package} />
        <StatTile label="Revenue, 30 days" value={formatCompactPrice(t.revenue_30d)} icon={IndianRupee} tone="brand" />
        <StatTile label="Reservations" value={formatNumber(t.reservations)} icon={ClipboardList} />
        <StatTile label="Delivery orders" value={formatNumber(t.orders)} icon={Package} />
        <StatTile label="Searches, 30 days" value={formatNumber(t.searches_30d)} icon={Search} />
        <StatTile label="Prices to review" value={t.open_price_flags} icon={Scale} tone="warning" href="/admin/anomalies" />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <section className="rounded-2xl border bg-card p-5">
          <h2 className="font-semibold">Sales across all shops</h2>
          <SalesChart data={d.sales_series} className="mt-4 h-56 w-full" />
        </section>
        <section className="rounded-2xl border bg-card p-5">
          <h2 className="font-semibold">Activity, last 14 days</h2>
          <ChartContainer config={activityConfig} className="mt-4 h-56 w-full">
            <BarChart data={activity} accessibilityLayer>
              <CartesianGrid vertical={false} strokeDasharray="3 3" />
              <XAxis dataKey="label" tickLine={false} axisLine={false} minTickGap={20} />
              <ChartTooltip content={<ChartTooltipContent />} />
              <ChartLegend content={<ChartLegendContent />} />
              <Bar dataKey="searches" fill="var(--color-searches)" radius={[4, 4, 0, 0]} />
              <Bar dataKey="inventory_updates" fill="var(--color-inventory_updates)" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ChartContainer>
        </section>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <section className="rounded-2xl border bg-card p-5">
          <h2 className="mb-4 font-semibold">Reservations by status</h2>
          <StatusBars data={d.reservations_by_status} labels={RESERVATION_LABELS} />
        </section>
        <section className="rounded-2xl border bg-card p-5">
          <h2 className="mb-4 font-semibold">Deliveries by status</h2>
          <StatusBars data={d.orders_by_status} labels={ORDER_LABELS} />
        </section>
        <section className="rounded-2xl border bg-card p-5">
          <h2 className="mb-4 font-semibold">Categories, 30 days</h2>
          <ul className="space-y-2.5">
            {d.categories.map((c) => (
              <li key={c.slug} className="text-sm">
                <div className="flex justify-between"><span>{c.name}</span><span className="text-muted-foreground tabular">{formatCompactPrice(c.revenue_30d)}</span></div>
                <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-muted">
                  <div className="h-full rounded-full" style={{ width: `${(c.revenue_30d / maxCat) * 100}%`, background: `oklch(0.65 0.13 ${c.color_hue})` }} />
                </div>
              </li>
            ))}
          </ul>
        </section>
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <section className="rounded-2xl border bg-card p-5 lg:col-span-1">
          <h2 className="mb-3 font-semibold">Top shops, 30 days</h2>
          <ol className="space-y-2">
            {d.top_shops.map((s, i) => (
              <li key={s.id} className="flex items-center gap-3 text-sm">
                <span className="w-4 text-muted-foreground tabular">{i + 1}</span>
                <Link href={`/shops/${s.slug}`} className="min-w-0 flex-1 truncate hover:underline">{s.name}</Link>
                <span className="text-muted-foreground tabular">{formatCompactPrice(s.revenue_30d)}</span>
              </li>
            ))}
          </ol>
        </section>
        <section className="rounded-2xl border bg-card p-5">
          <h2 className="mb-3 font-semibold">Popular searches</h2>
          <ol className="space-y-2">
            {d.popular_searches.map((p) => (
              <li key={p.query} className="flex justify-between gap-3 text-sm">
                <Link href={`/search?q=${encodeURIComponent(p.query)}`} className="truncate capitalize hover:underline">{p.query}</Link>
                <span className="shrink-0 text-muted-foreground tabular">{p.count}</span>
              </li>
            ))}
          </ol>
        </section>
        <section className="rounded-2xl border bg-card p-5">
          <h2 className="mb-1 font-semibold">Searches with no results</h2>
          <p className="mb-3 text-xs text-muted-foreground">Recruit shops or categories that meet this demand.</p>
          <ul className="flex flex-wrap gap-2">
            {d.zero_result_searches.map((z) => (
              <li key={z.query} className="rounded-full border px-3 py-1 text-sm capitalize">{z.query} <span className="text-muted-foreground tabular">· {z.count}</span></li>
            ))}
          </ul>
        </section>
      </div>
    </>
  );
}
