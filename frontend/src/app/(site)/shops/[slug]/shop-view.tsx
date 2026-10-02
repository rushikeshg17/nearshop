"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Bike, Calendar, Clock, Footprints, MapPin, Navigation, Phone, Search, Store } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { AppIcon } from "@/components/common/app-icon";
import { Freshness, OpenBadge, Rating, StockPill, VerifiedMark } from "@/components/common/indicators";
import { ProductThumb } from "@/components/common/product-thumb";
import { EmptyState, ErrorState } from "@/components/common/states";
import { ShopMap } from "@/components/map/shop-map";
import { ReviewList, Stars } from "@/components/shop/review-list";
import { ShopAvatar } from "@/components/shop/shop-card";
import { ShopTrust } from "@/components/shop/shop-trust";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useDebounce } from "@/hooks/use-debounce";
import { useMeta } from "@/hooks/use-session";
import { api, ApiError } from "@/lib/api";
import { formatDistance, formatPrice, travelHint } from "@/lib/format";
import { useLocation } from "@/lib/location";
import type { Listing, Review, ShopDetail } from "@/lib/types";
import { cn } from "@/lib/utils";

export function ShopView({ slug }: { slug: string }) {
  const params = useSearchParams();
  const { data: meta } = useMeta();
  const { location, ready } = useLocation();
  const [text, setText] = useState(params.get("q") ?? "");
  const [category, setCategory] = useState<string | null>(null);
  const [inStock, setInStock] = useState(false);
  const q = useDebounce(text, 250);

  const shop = useQuery({
    queryKey: ["shop", slug, location?.lat, location?.lng],
    queryFn: () => api.get<ShopDetail>(`/shops/${slug}`, { lat: location?.lat, lng: location?.lng }),
    enabled: ready,
  });
  const products = useQuery({
    queryKey: ["shop-products", slug, q, category, inStock],
    queryFn: () => api.get<{ items: Listing[]; total: number; category_counts: Record<string, number> }>(`/shops/${slug}/products`, { q, category, in_stock_only: inStock || undefined, page_size: 60 }),
    placeholderData: keepPreviousData,
  });
  const reviews = useQuery({
    queryKey: ["shop-reviews", slug],
    queryFn: () => api.get<{ reviews: Review[]; distribution: Record<string, number> }>(`/shops/${slug}/reviews`, { page_size: 8 }),
  });

  useEffect(() => {
    if (shop.data) document.title = `${shop.data.name}, ${shop.data.locality} · NearShop`;
  }, [shop.data]);

  if (shop.isError) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16">
        {shop.error instanceof ApiError && shop.error.status === 404 ? (
          <EmptyState icon={Store} title="Shop not found" description="It may have paused its listing." action={<Button asChild><Link href="/shops">Browse shops</Link></Button>} />
        ) : (
          <ErrorState error={shop.error} onRetry={() => shop.refetch()} />
        )}
      </div>
    );
  }
  const s = shop.data;
  if (!s) {
    return (
      <div className="mx-auto max-w-7xl space-y-6 px-4 pt-8 md:px-6">
        <Skeleton className="h-40 rounded-3xl" />
        <Skeleton className="h-64 rounded-3xl" />
      </div>
    );
  }
  const counts = products.data?.category_counts ?? {};

  return (
    <div className="mx-auto max-w-7xl px-4 pt-6 md:px-6 md:pt-10">
      <header className="grid gap-6 rounded-3xl border bg-card p-5 md:grid-cols-[1fr_320px] md:p-7">
        <div className="min-w-0">
          <div className="flex items-start gap-4">
            <ShopAvatar shop={s} categories={meta?.categories} className="size-16" />
            <div className="min-w-0">
              <h1 className="flex items-center gap-2 text-2xl font-semibold md:text-3xl">
                <span className="truncate">{s.name}</span>
                {s.is_verified && <VerifiedMark className="size-5" />}
              </h1>
              {s.tagline && <p className="text-muted-foreground">{s.tagline}</p>}
              <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-sm">
                <Rating value={s.rating_avg} count={s.rating_count} />
                <OpenBadge isOpen={s.is_open} label={s.hours_label} />
                <Freshness at={s.inventory_updated_at} prefix="Stock updated" />
              </div>
            </div>
          </div>
          {s.description && <p className="mt-5 max-w-2xl text-sm leading-relaxed text-muted-foreground">{s.description}</p>}
          <dl className="mt-5 grid gap-3 text-sm sm:grid-cols-2">
            <div className="flex gap-2"><MapPin className="mt-0.5 size-4 shrink-0 text-muted-foreground" /><dd>{s.address_line}{s.pincode && `, ${s.pincode}`}{s.distance_km !== null && <span className="text-muted-foreground"> · {formatDistance(s.distance_km)}, {travelHint(s.distance_km)}</span>}</dd></div>
            <div className="flex gap-2"><Clock className="mt-0.5 size-4 shrink-0 text-muted-foreground" /><dd>{s.opening_hours}{s.closed_on && ` · closed ${s.closed_on}s`}</dd></div>
            <div className="flex gap-2"><Footprints className="mt-0.5 size-4 shrink-0 text-muted-foreground" /><dd>Pickup: items held {s.hold_minutes} min after confirming</dd></div>
            <div className="flex gap-2">
              <Bike className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
              <dd>{s.offers_delivery ? `Delivers within ${s.delivery_radius_km} km · ${s.delivery_fee ? formatPrice(s.delivery_fee) : "free"}${s.free_delivery_above ? `, free above ${formatPrice(s.free_delivery_above)}` : ""}` : "Pickup only"}</dd>
            </div>
            {s.established_year && <div className="flex gap-2"><Calendar className="mt-0.5 size-4 shrink-0 text-muted-foreground" /><dd>Serving since {s.established_year}</dd></div>}
          </dl>
          <div className="mt-5 flex flex-wrap gap-2">
            <Button asChild variant="outline" size="sm"><a href={`https://www.openstreetmap.org/directions?to=${s.lat}%2C${s.lng}`} target="_blank" rel="noreferrer"><Navigation /> Directions</a></Button>
            {s.phone && <Button asChild variant="outline" size="sm"><a href={`tel:${s.phone}`}><Phone /> Call</a></Button>}
          </div>
        </div>
        <div className="h-56 overflow-hidden rounded-2xl border md:h-full md:min-h-60">
          <ShopMap className="h-full" center={s} zoom={15} fitToPoints={false} interactive={false}
            points={[{ id: s.id, lat: s.lat, lng: s.lng, label: s.name, title: s.name }]} selected={s.id} />
        </div>
      </header>

      <div className="mt-8 grid gap-8 lg:grid-cols-[1fr_340px]">
        <section className="min-w-0">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-xl font-semibold">On the shelf</h2>
              <p className="text-sm text-muted-foreground">{s.listing_counts?.in_stock ?? 0} of {s.listing_counts?.total ?? 0} items in stock right now</p>
            </div>
            <label className="flex items-center gap-2 text-sm"><Switch checked={inStock} onCheckedChange={setInStock} /> In stock only</label>
          </div>
          <div className="relative mt-4">
            <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={text} onChange={(e) => setText(e.target.value)} placeholder={`Search ${s.name}`} className="h-10 pl-9" />
          </div>
          {s.category_details.length > 1 && (
            <div className="mt-3 flex flex-wrap gap-2">
              <button onClick={() => setCategory(null)} className={cn("rounded-full border px-3 py-1 text-sm", !category ? "border-primary bg-primary text-primary-foreground" : "hover:bg-accent")}>All</button>
              {s.category_details.map((c) => (
                <button key={c.slug} onClick={() => setCategory(c.slug)} className={cn("inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-sm", category === c.slug ? "border-primary bg-primary text-primary-foreground" : "hover:bg-accent")}>
                  <AppIcon name={c.icon} className="size-3.5" /> {c.name} {counts[c.slug] ? <span className="opacity-60 tabular">{counts[c.slug]}</span> : null}
                </button>
              ))}
            </div>
          )}
          <ul className={cn("mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-3", products.isFetching && "opacity-70")}>
            {!products.data
              ? Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-28 rounded-2xl" />)
              : products.data.items.map((p) => (
                  <li key={p.id}>
                    <Link href={`/product/${p.id}`} className="flex h-full gap-3 rounded-2xl border bg-card p-3 transition-shadow hover:shadow-lift">
                      <ProductThumb icon={p.icon} imageUrl={p.image_url} category={p.category} alt="" size="md" />
                      <div className="min-w-0 flex-1">
                        <p className="line-clamp-2 text-sm leading-snug font-medium">{p.name}</p>
                        <p className="mt-1 font-semibold tabular">{formatPrice(p.price)}</p>
                        <StockPill status={p.stock_status} quantity={p.quantity} compact className="mt-1" />
                      </div>
                    </Link>
                  </li>
                ))}
          </ul>
          {products.data && !products.data.items.length && (
            <p className="mt-4 rounded-2xl border border-dashed p-8 text-center text-sm text-muted-foreground">Nothing matches here. <Link className="underline" href={`/search?q=${encodeURIComponent(text)}`}>Search all shops nearby</Link></p>
          )}
        </section>

        <aside className="space-y-6">
          <section className="rounded-3xl border bg-card p-5">
            <h2 className="mb-3 font-semibold">Track record</h2>
            <ShopTrust r={s.reliability} />
          </section>
          <section id="reviews" className="scroll-mt-20 rounded-3xl border bg-card p-5">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="font-semibold">Reviews</h2>
              {s.rating_avg && <span className="flex items-center gap-2 text-sm"><Stars value={Math.round(s.rating_avg)} /> {s.rating_avg.toFixed(1)}</span>}
            </div>
            {reviews.data ? <ReviewList reviews={reviews.data.reviews} /> : <Skeleton className="h-40" />}
          </section>
        </aside>
      </div>
    </div>
  );
}
