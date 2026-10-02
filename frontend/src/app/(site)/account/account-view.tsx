"use client";

import { useQuery } from "@tanstack/react-query";
import { History, Search, Sparkles, Star } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { ProductThumb } from "@/components/common/product-thumb";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { ActivityCard } from "@/components/fulfillment/activity-card";
import { ReviewDialog } from "@/components/fulfillment/review-dialog";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useMe } from "@/hooks/use-session";
import { api } from "@/lib/api";
import { formatDistance, formatPrice } from "@/lib/format";
import type { CustomerDashboard, Order, Reservation } from "@/lib/types";

const href = (i: Reservation | Order) => (i.kind === "reservation" ? `/account/reservations/${i.id}` : `/account/orders/${i.id}`);

export function AccountView() {
  const { data: me } = useMe();
  const [tab, setTab] = useState("all");
  const [reviewing, setReviewing] = useState<Reservation | Order | null>(null);
  const dash = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api.get<CustomerDashboard>("/me/dashboard"),
    enabled: me?.role === "customer",
    refetchInterval: 20_000,
  });

  if (me && me.role !== "customer") {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16">
        <EmptyState icon={History} title="This page is for customer accounts" description="Shop owners manage reservations from the shop dashboard."
          action={<Button asChild><Link href={me.role === "owner" ? "/shop" : "/admin"}>Go to dashboard</Link></Button>} />
      </div>
    );
  }

  const d = dash.data;
  const active = d ? [...d.active_reservations, ...d.active_orders] : [];
  const history = (d?.history ?? []).filter((h) => tab === "all" || h.kind === tab);

  return (
    <div className="mx-auto max-w-5xl px-4 pt-8 md:px-6 md:pt-12">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-muted-foreground">Your activity</p>
          <h1 className="text-3xl font-semibold">Hi {me?.name.split(" ")[0] ?? "there"}</h1>
        </div>
        {d && (
          <dl className="flex gap-6 text-sm">
            {[
              [d.stats.completed_pickups, "pickups"],
              [d.stats.delivered_orders, "deliveries"],
              [d.stats.shops_visited, "shops"],
            ].map(([n, l]) => (
              <div key={l as string}>
                <dt className="font-heading text-2xl font-semibold tabular">{n}</dt>
                <dd className="text-muted-foreground">{l}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>

      {dash.isError ? (
        <ErrorState className="mt-8" error={dash.error} onRetry={() => dash.refetch()} />
      ) : !d ? (
        <ListSkeleton className="mt-8" rows={3} />
      ) : (
        <div className="mt-8 grid gap-10 lg:grid-cols-[1fr_320px]">
          <div className="min-w-0 space-y-10">
            <section>
              <h2 className="mb-3 text-lg font-semibold">In progress</h2>
              {active.length ? (
                <div className="space-y-3">{active.map((i) => <ActivityCard key={`${i.kind}-${i.id}`} item={i} href={href(i)} />)}</div>
              ) : (
                <EmptyState icon={Search} title="Nothing on hold right now" description="Find something nearby and reserve it. The shop sets it aside for you."
                  action={<Button asChild><Link href="/search">Search nearby</Link></Button>} />
              )}
            </section>

            {d.to_review.length > 0 && (
              <section className="rounded-2xl border bg-brand-soft/40 p-4">
                <h2 className="flex items-center gap-2 font-semibold"><Star className="size-4 text-brand" /> Rate your recent visits</h2>
                <ul className="mt-3 space-y-2">
                  {d.to_review.map((i) => (
                    <li key={`${i.kind}-${i.id}`} className="flex items-center justify-between gap-3 rounded-xl bg-card p-3">
                      <span className="min-w-0 truncate text-sm">
                        <span className="font-medium">{i.shop.name}</span> · {i.kind === "reservation" ? i.product.name : `${i.items.length} items`}
                      </span>
                      <Button size="sm" onClick={() => setReviewing(i)}>Rate</Button>
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <section>
              <div className="mb-3 flex items-center justify-between gap-3">
                <h2 className="text-lg font-semibold">History</h2>
                <Tabs value={tab} onValueChange={setTab}>
                  <TabsList>
                    <TabsTrigger value="all">All</TabsTrigger>
                    <TabsTrigger value="reservation">Pickups</TabsTrigger>
                    <TabsTrigger value="order">Deliveries</TabsTrigger>
                  </TabsList>
                </Tabs>
              </div>
              {history.length ? (
                <div className="space-y-3">{history.map((i) => <ActivityCard key={`${i.kind}-${i.id}`} item={i} href={href(i)} />)}</div>
              ) : (
                <p className="rounded-2xl border border-dashed p-6 text-center text-sm text-muted-foreground">No past {tab === "order" ? "deliveries" : tab === "reservation" ? "pickups" : "activity"} yet.</p>
              )}
            </section>
          </div>

          <aside className="space-y-8">
            {d.recommendations.length > 0 && (
              <section>
                <h2 className="flex items-center gap-2 font-semibold"><Sparkles className="size-4 text-brand" /> You might need next</h2>
                <p className="mt-1 text-xs text-muted-foreground">Based on what people buy along with your recent purchases.</p>
                <ul className="mt-3 space-y-2">
                  {d.recommendations.map((r) => (
                    <li key={r.offer.id}>
                      <Link href={`/product/${r.offer.id}`} className="flex items-center gap-3 rounded-xl border bg-card p-3 hover:bg-accent/50">
                        <ProductThumb icon={r.offer.icon} imageUrl={r.offer.image_url} category={r.offer.category} alt="" size="sm" />
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-medium">{r.offer.name}</span>
                          <span className="block truncate text-xs text-muted-foreground">{r.offer.shop.name} · {formatDistance(r.offer.shop.distance_km)}</span>
                        </span>
                        <span className="text-sm font-semibold tabular">{formatPrice(r.offer.price)}</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </section>
            )}
            {d.recent_searches.length > 0 && (
              <section>
                <h2 className="font-semibold">Recent searches</h2>
                <div className="mt-3 flex flex-wrap gap-2">
                  {d.recent_searches.map((q) => (
                    <Link key={q} href={`/search?q=${encodeURIComponent(q)}`} className="rounded-full border bg-card px-3 py-1.5 text-sm hover:bg-accent">{q}</Link>
                  ))}
                </div>
              </section>
            )}
          </aside>
        </div>
      )}
      {reviewing && <ReviewDialog item={reviewing} open onOpenChange={(o) => !o && setReviewing(null)} />}
    </div>
  );
}
