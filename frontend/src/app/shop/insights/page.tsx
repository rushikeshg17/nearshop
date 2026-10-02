"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowDownRight, ArrowRight, ArrowUpRight, BrainCircuit, Info, PackagePlus, Scale, SearchX, TrendingUp, Users } from "lucide-react";
import Link from "next/link";

import { AppIcon } from "@/components/common/app-icon";
import { ProductThumb } from "@/components/common/product-thumb";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { PageTitle } from "@/components/dashboard/dashboard-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { formatPrice, timeAgo } from "@/lib/format";
import type { ModelSummary, OwnerInsights } from "@/lib/types";
import { cn } from "@/lib/utils";

function ModelNote({ m, children }: { m?: ModelSummary; children: React.ReactNode }) {
  if (!m) return null;
  return (
    <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
      <BrainCircuit className="size-3.5 text-brand" /> {m.algorithm} · trained {timeAgo(m.trained_at)} · {children}
      {m.uses_demo_data && <Badge variant="outline" className="h-5 text-[10px]">Demo data</Badge>}
    </p>
  );
}

export default function InsightsPage() {
  const q = useQuery({ queryKey: ["owner", "insights"], queryFn: () => api.get<OwnerInsights>("/owner/insights") });
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const d = q.data;
  if (!d) return <ListSkeleton rows={5} />;
  const demand = d.models.demand;
  const dm = demand?.metrics as { mae_7d?: number; naive_mae_7d?: number; improvement_pct?: number } | undefined;

  return (
    <>
      <PageTitle title="AI insights" description="What to restock, what people nearby are looking for, and which prices customers may question." />

      <section className="rounded-2xl border bg-card">
        <div className="border-b p-5">
          <h2 className="flex items-center gap-2 text-lg font-semibold"><TrendingUp className="size-5 text-brand" /> Restock before you run out</h2>
          <ModelNote m={demand}>
            {dm?.mae_7d !== undefined && <>average error {dm.mae_7d} units per week ({dm.improvement_pct}% better than &ldquo;same as last week&rdquo;)</>}
          </ModelNote>
        </div>
        {d.restock.length ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Product</TableHead>
                <TableHead className="text-right">In stock</TableHead>
                <TableHead className="text-right">Next 7 days</TableHead>
                <TableHead className="text-right">Runs out in</TableHead>
                <TableHead className="text-right">Suggested order</TableHead>
                <TableHead className="hidden md:table-cell">Trend</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {d.restock.map((r) => (
                <TableRow key={r.id}>
                  <TableCell>
                    <Link href={`/shop/inventory?focus=${r.id}`} className="flex items-center gap-2 hover:underline">
                      <ProductThumb icon={r.icon} imageUrl={r.image_url} category={r.category} alt="" size="sm" className="size-8 [&_svg]:size-4" />
                      <span className="max-w-60 truncate">{r.name}</span>
                    </Link>
                  </TableCell>
                  <TableCell className="text-right tabular">{r.quantity}</TableCell>
                  <TableCell className="text-right tabular">~{Math.round(r.predicted_7d)}</TableCell>
                  <TableCell className={cn("text-right tabular", (r.days_to_stockout ?? 99) < 4 && "font-semibold text-destructive")}>
                    {r.days_to_stockout === null ? "-" : r.quantity === 0 ? "Out now" : `${Math.max(0, Math.round(r.days_to_stockout))} days`}
                  </TableCell>
                  <TableCell className="text-right font-medium tabular">{r.recommended_restock || "-"}</TableCell>
                  <TableCell className="hidden md:table-cell">
                    <span className={cn("inline-flex items-center gap-1 text-xs", r.trend === "rising" ? "text-success-ink" : r.trend === "falling" ? "text-muted-foreground" : "")}>
                      {r.trend === "rising" ? <ArrowUpRight className="size-3.5" /> : r.trend === "falling" ? <ArrowDownRight className="size-3.5" /> : null}
                      {r.trend} · {r.confidence} confidence
                    </span>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <p className="p-6 text-sm text-muted-foreground">Nothing is at risk of running out in the next two weeks.</p>
        )}
      </section>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <section className="rounded-2xl border bg-card p-5">
          <h2 className="flex items-center gap-2 font-semibold"><Users className="size-4 text-brand" /> What people within 3 km search for</h2>
          <p className="mt-1 text-xs text-muted-foreground">Last 14 days of searches near your shop.</p>
          <ul className="mt-4 space-y-2">
            {d.area_demand.map((a) => (
              <li key={a.query} className="flex items-center justify-between gap-3 text-sm">
                <span className="truncate capitalize">{a.query}</span>
                <span className="flex shrink-0 items-center gap-2">
                  <span className="text-muted-foreground tabular">{a.searches} searches</span>
                  {a.you_stock_it ? <Badge variant="secondary">You stock it</Badge> : <Badge className="bg-warning-soft text-warning-ink">Opportunity</Badge>}
                </span>
              </li>
            ))}
            {!d.area_demand.length && <li className="text-sm text-muted-foreground">No searches nearby yet.</li>}
          </ul>
        </section>

        <section className="rounded-2xl border bg-card p-5">
          <h2 className="flex items-center gap-2 font-semibold"><SearchX className="size-4 text-brand" /> Searched nearby, found nowhere</h2>
          <p className="mt-1 text-xs text-muted-foreground">Demand no shop in the area is meeting. Worth stocking?</p>
          <ul className="mt-4 flex flex-wrap gap-2">
            {d.missed_demand.map((m) => (
              <li key={m.query} className="rounded-full border px-3 py-1 text-sm capitalize">{m.query} <span className="text-muted-foreground tabular">· {m.searches}</span></li>
            ))}
            {!d.missed_demand.length && <li className="text-sm text-muted-foreground">Nothing unmet right now.</li>}
          </ul>
        </section>

        <section className="rounded-2xl border bg-card p-5">
          <h2 className="flex items-center gap-2 font-semibold"><PackagePlus className="size-4 text-brand" /> Bought together, but you don&apos;t stock it</h2>
          <ModelNote m={d.models.recommendations}>market-basket rules from nearby purchases</ModelNote>
          <ul className="mt-4 divide-y">
            {d.bundle_gaps.map((g) => (
              <li key={g.item.id} className="flex items-center gap-3 py-2.5 first:pt-0">
                <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-muted"><AppIcon name={g.item.icon} className="size-4" /></span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{g.item.name}</p>
                  <p className="truncate text-xs text-muted-foreground">
                    {Math.round(g.confidence * 100)}% of people buying {g.because_of} also buy this
                  </p>
                </div>
                {g.item.typical_price && <span className="text-xs text-muted-foreground tabular">{formatPrice(g.item.typical_price)}</span>}
              </li>
            ))}
            {!d.bundle_gaps.length && <li className="text-sm text-muted-foreground">Your range already covers the common bundles.</li>}
          </ul>
          {d.bundle_gaps.length > 0 && (
            <Button asChild variant="outline" size="sm" className="mt-3"><Link href="/shop/catalog">Add from catalogue <ArrowRight /></Link></Button>
          )}
        </section>

        <section className="rounded-2xl border bg-card p-5">
          <h2 className="flex items-center gap-2 font-semibold"><Scale className="size-4 text-brand" /> Prices customers may question</h2>
          <ModelNote m={d.models.anomalies}>compared with other shops selling the same item</ModelNote>
          <ul className="mt-4 divide-y">
            {d.price_flags.map((f) => (
              <li key={f.id} className="flex items-center gap-3 py-2.5 first:pt-0">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{f.product.name}</p>
                  <p className="text-xs text-muted-foreground">
                    Yours {formatPrice(f.price)} · typical {formatPrice(f.reference_price)} across {f.peer_count} shops
                  </p>
                </div>
                <Badge className={f.direction === "high" ? "bg-warning-soft text-warning-ink" : "bg-info-soft text-info-ink"}>
                  {f.deviation_pct > 0 ? "+" : ""}{f.deviation_pct}%
                </Badge>
              </li>
            ))}
            {!d.price_flags.length && <li className="text-sm text-muted-foreground">Your prices are in line with shops nearby.</li>}
          </ul>
          <p className="mt-3 flex gap-1.5 text-xs text-muted-foreground"><Info className="mt-0.5 size-3.5 shrink-0" /> Flags are for your review only. NearShop never hides or penalises a listing automatically.</p>
        </section>
      </div>
    </>
  );
}
