"use client";

import { Check, Clock3, PackageCheck, RefreshCw, Star, Truck } from "lucide-react";

import { useNow } from "@/hooks/use-debounce";
import { timeAgo } from "@/lib/format";
import type { Reliability } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Factual trust signals. Every number is something the customer can understand, no opaque score. */
export function ShopTrust({ r, className }: { r: Reliability; className?: string }) {
  const now = useNow(60_000);
  const facts = [
    {
      icon: RefreshCw,
      label: "Inventory updated",
      value: r.inventory_updated_at ? timeAgo(r.inventory_updated_at, now) : "Not yet",
      sub: r.inventory_update_days_7d ? `on ${r.inventory_update_days_7d} of the last 7 days` : "No updates this week",
      good: r.frequently_updated,
    },
    {
      icon: PackageCheck,
      label: "Reservations confirmed",
      value: r.reservation_requests_90d ? `${r.reservations_confirmed_90d} of ${r.reservation_requests_90d}` : "New shop",
      sub: r.acceptance_rate !== null ? `${Math.round(r.acceptance_rate * 100)}% in the last 90 days` : "No requests yet",
      good: (r.acceptance_rate ?? 0) >= 0.9,
    },
    {
      icon: Clock3,
      label: "Typical confirmation",
      value: r.median_response_minutes !== null ? `${Math.max(1, r.median_response_minutes)} min` : "No data",
      sub: "from request to 'held for you'",
      good: (r.median_response_minutes ?? 99) <= 10,
    },
    {
      icon: Star,
      label: "Customer rating",
      value: r.rating_avg ? `${r.rating_avg.toFixed(1)} / 5` : "No reviews",
      sub: r.rating_count ? `${r.rating_count} verified purchases${r.accuracy_avg ? `, accuracy ${r.accuracy_avg.toFixed(1)}` : ""}` : "Reviews come from completed purchases only",
      good: (r.rating_avg ?? 0) >= 4.3,
    },
  ];
  return (
    <div className={cn("space-y-4", className)}>
      {r.highlights.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {r.highlights.map((h) => (
            <li key={h} className="inline-flex items-center gap-1.5 rounded-full bg-success-soft px-3 py-1 text-xs font-medium text-success-ink">
              <Check className="size-3.5" /> {h}
            </li>
          ))}
        </ul>
      )}
      <dl className="grid grid-cols-2 gap-3">
        {facts.map((f) => (
          <div key={f.label} className="rounded-xl border bg-card p-3">
            <dt className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <f.icon className={cn("size-3.5", f.good && "text-success")} /> {f.label}
            </dt>
            <dd className="mt-1 text-sm font-semibold tabular" suppressHydrationWarning>{f.value}</dd>
            <dd className="text-xs text-muted-foreground">{f.sub}</dd>
          </div>
        ))}
      </dl>
      {(r.orders_delivered_90d > 0 || r.shop_cancellations_90d > 0) && (
        <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Truck className="size-3.5" />
          {r.orders_delivered_90d} deliveries completed and {r.shop_cancellations_90d} cancelled by the shop in the last 90 days.
        </p>
      )}
    </div>
  );
}
