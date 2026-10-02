"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  BellRing,
  Bike,
  BrainCircuit,
  Check,
  ClipboardCheck,
  Footprints,
  PackageSearch,
  Search,
  ShieldCheck,
  Store,
  TrendingUp,
} from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";

import { AppIcon } from "@/components/common/app-icon";
import { Freshness, StockPill } from "@/components/common/indicators";
import { ProductThumb } from "@/components/common/product-thumb";
import { ShopCard } from "@/components/shop/shop-card";
import { LocationPicker } from "@/components/site/location-picker";
import { SearchBox } from "@/components/site/search-box";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useMeta } from "@/hooks/use-session";
import { api } from "@/lib/api";
import { formatDistance, formatNumber, formatPrice } from "@/lib/format";
import { useLocation } from "@/lib/location";
import type { SearchResponse, ShopBrief } from "@/lib/types";

const QUICK = ["phone charger", "PVC elbow joint", "school shoes", "9W LED bulb", "umbrella", "bike engine oil"];

// Above the fold: animate on mount (never depend on scroll to reveal the hero).
const fadeUpNow = {
  initial: { opacity: 0, y: 16 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] as const },
};

const fadeUp = {
  initial: { opacity: 0, y: 16 },
  whileInView: { opacity: 1, y: 0 },
  viewport: { once: true, margin: "-60px" },
  transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] as const },
};

export function HomeView() {
  const { data: meta } = useMeta();
  const { location, radiusKm, ready } = useLocation();

  const live = useQuery({
    queryKey: ["home-live", location?.lat, location?.lng],
    queryFn: () =>
      api.get<SearchResponse>("/search", { q: "fast charger", lat: location!.lat, lng: location!.lng, radius_km: 6, page_size: 3 }),
    enabled: ready,
    staleTime: 5 * 60_000,
  });
  const shops = useQuery({
    queryKey: ["shops", "near", location?.lat, location?.lng, radiusKm],
    queryFn: () => api.get<{ shops: ShopBrief[] }>("/shops", { lat: location!.lat, lng: location!.lng, radius_km: Math.max(radiusKm, 4) }),
    enabled: ready,
  });

  return (
    <>
      {/* ---------------------------------------------------------------- hero */}
      <section className="relative overflow-hidden border-b">
        <div className="bg-dots absolute inset-0 [mask-image:radial-gradient(ellipse_at_30%_20%,black,transparent_70%)]" aria-hidden />
        <div className="relative mx-auto grid max-w-7xl gap-12 px-4 pt-12 pb-16 md:px-6 md:pt-20 md:pb-24 lg:grid-cols-[1.15fr_1fr] lg:items-center">
          <div>
            <motion.div {...fadeUpNow} className="mb-5">
              <LocationPicker />
            </motion.div>
            <motion.h1
              {...fadeUpNow}
              transition={{ ...fadeUpNow.transition, delay: 0.05 }}
              className="text-[2.6rem] leading-[1.02] font-semibold sm:text-6xl lg:text-[3.6rem] xl:text-7xl"
            >
              Find it nearby.
              <span className="block text-muted-foreground">Skip the five-shop hunt.</span>
            </motion.h1>
            <motion.p
              {...fadeUpNow}
              transition={{ ...fadeUpNow.transition, delay: 0.1 }}
              className="mt-5 max-w-xl text-base text-muted-foreground md:text-lg"
            >
              See which shops around you have it on the shelf right now, what they charge, and how fresh that stock count is.
              Reserve it and walk in, or let the shop deliver.
            </motion.p>
            <motion.div {...fadeUpNow} transition={{ ...fadeUpNow.transition, delay: 0.15 }} className="mt-8 max-w-xl">
              <SearchBox size="lg" placeholder="Try 'phone charging adapter' or 'tap leaking'" />
              <div className="mt-4 flex flex-wrap gap-2">
                {QUICK.map((q) => (
                  <Link
                    key={q}
                    href={`/search?q=${encodeURIComponent(q)}`}
                    className="rounded-full border bg-card px-3 py-1.5 text-sm text-muted-foreground transition-colors hover:border-foreground/20 hover:text-foreground"
                  >
                    {q}
                  </Link>
                ))}
              </div>
            </motion.div>
            {meta && (
              <motion.dl
                {...fadeUpNow}
                transition={{ ...fadeUpNow.transition, delay: 0.2 }}
                className="mt-10 flex flex-wrap gap-x-8 gap-y-3 text-sm"
              >
                {[
                  [formatNumber(meta.stats.shops), `local shops in ${meta.city.name}`],
                  [formatNumber(meta.stats.in_stock), "items in stock right now"],
                  ["0", "delivery riders needed"],
                ].map(([n, l]) => (
                  <div key={l} className="flex items-baseline gap-2">
                    <dt className="font-heading text-2xl font-semibold tabular">{n}</dt>
                    <dd className="text-muted-foreground">{l}</dd>
                  </div>
                ))}
              </motion.dl>
            )}
          </div>

          {/* Live proof: real results from the API, not a mockup */}
          <motion.div
            initial={{ opacity: 0, scale: 0.97, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
            className="relative hidden lg:block"
          >
            <div className="absolute -inset-6 rounded-[2.5rem] bg-gradient-to-b from-brand/10 to-transparent blur-2xl" aria-hidden />
            <div className="relative rounded-3xl border bg-card/90 p-4 shadow-lift backdrop-blur">
              <div className="flex items-center gap-2 rounded-xl border bg-background px-3 py-2.5 text-sm">
                <Search className="size-4 text-muted-foreground" />
                <span>fast charger</span>
                <span className="ml-auto text-xs text-muted-foreground">
                  {live.data ? `${live.data.total} items · ${live.data.shops.length} shops` : "searching..."}
                </span>
              </div>
              <ul className="mt-3 space-y-2">
                {live.isLoading || !live.data
                  ? Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-[88px] rounded-2xl" />)
                  : live.data.groups.map((g, i) => (
                      <motion.li
                        key={g.key}
                        initial={{ opacity: 0, x: 16 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: 0.4 + i * 0.12, duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
                      >
                        <Link
                          href={`/product/${g.best_offer.id}`}
                          className="flex items-center gap-3 rounded-2xl border bg-background p-3 transition-colors hover:bg-accent/60"
                        >
                          <ProductThumb icon={g.icon} category={g.category} imageUrl={g.image_url} alt="" size="md" />
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-semibold">{g.name}</p>
                            <p className="mt-0.5 truncate text-xs text-muted-foreground">
                              {g.best_offer.shop.name} · {formatDistance(g.best_offer.shop.distance_km)}
                              {g.shop_count > 1 && ` · +${g.shop_count - 1} more shops`}
                            </p>
                            <div className="mt-1.5 flex items-center gap-2">
                              <StockPill status={g.best_offer.stock_status} quantity={g.best_offer.quantity} compact />
                              <Freshness at={g.best_offer.stock_updated_at} />
                            </div>
                          </div>
                          <p className="self-start font-semibold tabular">{formatPrice(g.min_price)}</p>
                        </Link>
                      </motion.li>
                    ))}
              </ul>
              <div className="mt-3 flex items-center justify-between rounded-xl bg-brand-soft px-3 py-2.5 text-sm text-brand-ink">
                <span className="inline-flex items-center gap-2 font-medium">
                  <Footprints className="size-4" /> Reserve now, pick up in 30 min
                </span>
                <ArrowRight className="size-4" />
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* ---------------------------------------------------------------- categories */}
      <section className="mx-auto max-w-7xl px-4 pt-14 md:px-6">
        <div className="mb-6 flex items-end justify-between">
          <div>
            <h2 className="text-2xl font-semibold md:text-3xl">Browse by what you need</h2>
            <p className="mt-1 text-muted-foreground">The everyday things that are hard to find online and easy to find nearby.</p>
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {(meta?.categories ?? Array.from({ length: 10 }).map(() => null)).map((c, i) =>
            c ? (
              <motion.div key={c.slug} {...fadeUp} transition={{ ...fadeUp.transition, delay: i * 0.03 }}>
                <Link
                  href={`/search?category=${c.slug}`}
                  className="group flex h-full flex-col gap-3 rounded-2xl border bg-card p-4 transition-[transform,box-shadow] duration-200 hover:-translate-y-0.5 hover:shadow-lift"
                >
                  <span
                    className="grid size-11 place-items-center rounded-xl transition-transform duration-300 group-hover:scale-105"
                    style={{
                      background: `light-dark(oklch(0.95 0.035 ${c.color_hue}), oklch(0.3 0.045 ${c.color_hue}))`,
                      color: `light-dark(oklch(0.5 0.12 ${c.color_hue}), oklch(0.82 0.09 ${c.color_hue}))`,
                    }}
                  >
                    <AppIcon name={c.icon} className="size-5" />
                  </span>
                  <span>
                    <span className="block font-medium">{c.name}</span>
                    <span className="text-xs text-muted-foreground tabular">{formatNumber(c.in_stock_listings ?? 0)} in stock</span>
                  </span>
                </Link>
              </motion.div>
            ) : (
              <Skeleton key={i} className="h-[118px] rounded-2xl" />
            ),
          )}
        </div>
      </section>

      {/* ---------------------------------------------------------------- nearby shops */}
      <section className="mx-auto max-w-7xl px-4 pt-16 md:px-6">
        <div className="mb-6 flex items-end justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold md:text-3xl">Shops near {location?.label ?? "you"}</h2>
            <p className="mt-1 text-muted-foreground">Sorted by distance. The freshness line tells you how recently they counted their shelves.</p>
          </div>
          <Button asChild variant="outline" className="hidden rounded-full sm:inline-flex">
            <Link href="/shops">
              See map <ArrowRight />
            </Link>
          </Button>
        </div>
        <div className="-mx-4 flex snap-x gap-3 overflow-x-auto px-4 pb-2 scrollbar-none md:mx-0 md:grid md:grid-cols-3 md:overflow-visible md:px-0 lg:grid-cols-4">
          {shops.isLoading || !shops.data
            ? Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-44 w-72 shrink-0 rounded-2xl md:w-auto" />)
            : shops.data.shops.slice(0, 8).map((s) => (
                <ShopCard key={s.id} shop={s} categories={meta?.categories} className="w-72 shrink-0 snap-start md:w-auto" />
              ))}
        </div>
      </section>

      {/* ---------------------------------------------------------------- how it works */}
      <section id="how" className="mx-auto max-w-7xl scroll-mt-20 px-4 pt-20 md:px-6">
        <motion.div {...fadeUp} className="max-w-2xl">
          <h2 className="text-2xl font-semibold md:text-3xl">Check the shelf before you leave home</h2>
          <p className="mt-2 text-muted-foreground">
            Pickup is the default because you get to see it before you pay. Delivery is there when the shop offers it, handled by the shop itself.
          </p>
        </motion.div>
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          {[
            { icon: PackageSearch, title: "Search the way you talk", body: "Type 'charging adapter' or 'tap leaking'. NearShop understands meaning, not just exact product names.", tag: "AI search" },
            { icon: ClipboardCheck, title: "Reserve in one tap", body: "The shop confirms and sets it aside for 30 minutes. You get a pickup code and a live countdown.", tag: "No payment upfront" },
            { icon: Footprints, title: "Walk in, check, pay", body: "Inspect it at the counter and pay there. If the shop delivers, cash on delivery works too.", tag: "Pickup or delivery" },
          ].map((s, i) => (
            <motion.div key={s.title} {...fadeUp} transition={{ ...fadeUp.transition, delay: i * 0.08 }} className="relative rounded-2xl border bg-card p-6">
              <span className="absolute top-6 right-6 font-heading text-4xl font-semibold text-muted-foreground/20 tabular">0{i + 1}</span>
              <s.icon className="size-6 text-brand" />
              <h3 className="mt-4 text-lg font-semibold">{s.title}</h3>
              <p className="mt-1.5 text-sm text-muted-foreground">{s.body}</p>
              <span className="mt-4 inline-flex rounded-full bg-muted px-2.5 py-1 text-xs font-medium">{s.tag}</span>
            </motion.div>
          ))}
        </div>
      </section>

      {/* ---------------------------------------------------------------- for shops */}
      <section className="mx-auto max-w-7xl px-4 pt-20 md:px-6">
        <motion.div {...fadeUp} className="overflow-hidden rounded-3xl bg-primary text-primary-foreground">
          <div className="grid gap-10 p-8 md:p-12 lg:grid-cols-[1.1fr_1fr]">
            <div>
              <span className="inline-flex items-center gap-2 rounded-full bg-primary-foreground/10 px-3 py-1 text-xs font-medium">
                <Store className="size-3.5" /> For shop owners
              </span>
              <h2 className="mt-4 text-3xl font-semibold md:text-4xl">Your shelf, online by this evening.</h2>
              <p className="mt-3 max-w-lg text-primary-foreground/70">
                Pick products from a ready catalogue, set your price and count. Customers nearby find you, reserve, and walk in ready to buy.
              </p>
              <div className="mt-8 flex flex-wrap gap-3">
                <Button asChild size="lg" className="h-11 rounded-full bg-brand px-6 text-brand-foreground hover:bg-brand/90">
                  <Link href="/register/shop">
                    List your shop free <ArrowRight />
                  </Link>
                </Button>
                <Button asChild size="lg" variant="ghost" className="h-11 rounded-full px-5 text-primary-foreground hover:bg-primary-foreground/10 hover:text-primary-foreground">
                  <Link href="/login?next=/shop">See the dashboard</Link>
                </Button>
              </div>
            </div>
            <ul className="grid gap-3 sm:grid-cols-2">
              {[
                { icon: BellRing, t: "Reservation alerts", d: "Confirm or decline with one tap." },
                { icon: TrendingUp, t: "Restock forecasts", d: "Know what will run out next week." },
                { icon: BrainCircuit, t: "Local demand", d: "See what people nearby search for." },
                { icon: ShieldCheck, t: "Earn trust", d: "Fresh stock counts rank you higher." },
                { icon: Bike, t: "Your delivery, your rules", d: "Set radius, fee and free-delivery limit." },
                { icon: Check, t: "No commission to start", d: "Pay at the counter, as always." },
              ].map((f) => (
                <li key={f.t} className="rounded-2xl bg-primary-foreground/[0.06] p-4">
                  <f.icon className="size-5 text-brand" />
                  <p className="mt-3 text-sm font-medium">{f.t}</p>
                  <p className="mt-0.5 text-sm text-primary-foreground/60">{f.d}</p>
                </li>
              ))}
            </ul>
          </div>
        </motion.div>
      </section>
    </>
  );
}
