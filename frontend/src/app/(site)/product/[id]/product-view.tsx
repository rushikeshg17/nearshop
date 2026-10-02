"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ArrowRight,
  Bike,
  ChevronRight,
  Footprints,
  MapPin,
  Navigation,
  PackageX,
  Phone,
  Sparkles,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Distance, Freshness, OpenBadge, Price, Rating, StockPill, VerifiedMark } from "@/components/common/indicators";
import { ProductThumb } from "@/components/common/product-thumb";
import { EmptyState, ErrorState } from "@/components/common/states";
import { StatusBadge } from "@/components/common/status";
import { ShopMap } from "@/components/map/shop-map";
import { DeliveryDialog } from "@/components/product/delivery-dialog";
import { ReserveDialog } from "@/components/product/reserve-dialog";
import { ReviewList } from "@/components/shop/review-list";
import { ShopTrust } from "@/components/shop/shop-trust";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useMe } from "@/hooks/use-session";
import { api, ApiError } from "@/lib/api";
import { formatDistance, formatPrice, travelHint } from "@/lib/format";
import { useLocation } from "@/lib/location";
import type { ProductDetail, Recommendation } from "@/lib/types";
import { cn } from "@/lib/utils";

export function ProductView({ id }: { id: number }) {
  const router = useRouter();
  const pathname = usePathname();
  const { location, ready } = useLocation();
  const { data: me } = useMe();
  const [reserveOpen, setReserveOpen] = useState(false);
  const [deliveryOpen, setDeliveryOpen] = useState(false);

  const q = useQuery({
    queryKey: ["product", id, location?.lat, location?.lng],
    queryFn: () => api.get<ProductDetail>(`/products/${id}`, { lat: location?.lat, lng: location?.lng }),
    enabled: ready,
  });
  const recs = useQuery({
    queryKey: ["product-recs", id, location?.lat, location?.lng],
    queryFn: () => api.get<{ source: "apriori" | "popular"; items: Recommendation[] }>(`/products/${id}/recommendations`, { lat: location?.lat, lng: location?.lng }),
    enabled: ready,
  });

  const p = q.data;
  useEffect(() => {
    if (p) document.title = `${p.name} at ${p.shop.name} · NearShop`;
  }, [p]);

  function requireCustomer(open: () => void) {
    if (!me) {
      router.push(`/login?next=${encodeURIComponent(pathname)}`);
      return;
    }
    open();
  }

  if (q.isError) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16">
        {q.error instanceof ApiError && q.error.status === 404 ? (
          <EmptyState icon={PackageX} title="This listing is gone" description="The shop may have removed it. Search to find it elsewhere nearby."
            action={<Button asChild><Link href="/search">Search nearby</Link></Button>} />
        ) : (
          <ErrorState error={q.error} onRetry={() => q.refetch()} />
        )}
      </div>
    );
  }
  if (!p) return <ProductSkeleton />;

  const out = p.quantity <= 0;
  const isCustomer = !me || me.role === "customer";
  const insight = p.price_insight;
  const shop = p.shop;
  const delivery = p.delivery_quote;

  return (
    <div className="mx-auto max-w-7xl px-4 pt-4 md:px-6 md:pt-8">
      <nav aria-label="Breadcrumb" className="mb-5 flex items-center gap-1 text-sm text-muted-foreground">
        <Link href={`/search?category=${p.category_detail.slug}`} className="hover:text-foreground">{p.category_detail.name}</Link>
        {p.subcategory && (
          <>
            <ChevronRight className="size-3.5" />
            <Link href={`/search?q=${encodeURIComponent(p.subcategory.replace(/-/g, " "))}`} className="capitalize hover:text-foreground">
              {p.subcategory.replace(/-/g, " ")}
            </Link>
          </>
        )}
      </nav>

      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_360px] lg:gap-10 xl:grid-cols-[minmax(0,1fr)_400px] xl:gap-14">
        {/* ---------------------------------------------------------- left: item */}
        <div className="min-w-0 space-y-10">
          <div className="grid gap-6 sm:grid-cols-[200px_minmax(0,1fr)] sm:items-start xl:grid-cols-[260px_minmax(0,1fr)]">
            <motion.div initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.4 }}>
              <ProductThumb icon={p.icon} imageUrl={p.image_url} hue={p.category_detail.color_hue} alt={p.name} size="xl" className="max-sm:mx-auto max-sm:max-w-56" />
            </motion.div>
            <div>
              {p.brand && <p className="text-sm font-medium tracking-wide text-muted-foreground uppercase">{p.brand}</p>}
              <h1 className="mt-1 text-2xl leading-tight font-semibold md:text-3xl">{p.name}</h1>
              {p.unit && <p className="mt-1 text-sm text-muted-foreground">{p.unit}</p>}
              {p.description && <p className="mt-4 text-[15px] leading-relaxed text-muted-foreground">{p.description}</p>}
              {Object.keys(p.specs).length > 0 && (
                <dl className="mt-5 grid grid-cols-1 gap-x-6 gap-y-2 text-sm 2xl:grid-cols-2">
                  {Object.entries(p.specs).map(([k, v]) => (
                    <div key={k} className="flex justify-between gap-4 border-b border-dashed pb-2">
                      <dt className="text-muted-foreground">{k}</dt>
                      <dd className="text-right font-medium">{v}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </div>
          </div>

          {/* compare */}
          <section id="compare" className="scroll-mt-20">
            <h2 className="text-xl font-semibold">Compare shops nearby</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              {p.other_offers.length ? `${p.other_offers.length + 1} shops list this item.` : "Only this shop lists this item right now."}
              {insight?.median && ` Typical price ${formatPrice(insight.median)}.`}
            </p>
            {p.other_offers.length > 0 && (
              <div className="mt-4 overflow-hidden rounded-2xl border">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/40 hover:bg-muted/40">
                      <TableHead>Shop</TableHead>
                      <TableHead className="text-right">Price</TableHead>
                      <TableHead className="hidden sm:table-cell">Stock</TableHead>
                      <TableHead className="text-right">Distance</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {[{ ...p, shop: shop as ProductDetail["shop"] }, ...p.other_offers].map((o, i) => (
                      <TableRow key={o.id} className={cn(i === 0 && "bg-brand-soft/40 hover:bg-brand-soft/50")}>
                        <TableCell className="max-w-48">
                          <Link href={`/product/${o.id}`} className="block truncate font-medium hover:underline">{o.shop.name}</Link>
                          <span className="flex items-center gap-2 text-xs text-muted-foreground">
                            {i === 0 ? "You're viewing" : o.shop.locality}
                            <Rating value={o.shop.rating_avg} count={o.shop.rating_count} showCount={false} />
                          </span>
                        </TableCell>
                        <TableCell className="text-right font-semibold tabular">{formatPrice(o.price)}</TableCell>
                        <TableCell className="hidden sm:table-cell">
                          <div className="flex flex-col items-start gap-1">
                            <StockPill status={o.stock_status} quantity={o.quantity} compact />
                            <Freshness at={o.stock_updated_at} />
                          </div>
                        </TableCell>
                        <TableCell className="text-right text-sm tabular">{formatDistance(o.shop.distance_km) || "-"}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </section>

          {/* recommendations */}
          {recs.data && recs.data.items.length > 0 && (
            <section>
              <div className="flex items-center gap-2">
                <h2 className="text-xl font-semibold">{recs.data.source === "apriori" ? "Often bought together" : `Popular in ${p.category_detail.name}`}</h2>
                {recs.data.source === "apriori" && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-brand-soft px-2 py-0.5 text-xs font-medium text-brand-ink">
                    <Sparkles className="size-3" /> Market-basket AI
                  </span>
                )}
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                {recs.data.source === "apriori"
                  ? "Learned from what customers nearby buy in the same visit. Save a second trip."
                  : "Bestsellers in this category near you."}
              </p>
              <ul className="mt-4 grid gap-3 sm:grid-cols-2">
                {recs.data.items.map((r) => (
                  <li key={r.offer.id}>
                    <Link href={`/product/${r.offer.id}`} className="flex items-center gap-3 rounded-2xl border bg-card p-3 transition-shadow hover:shadow-lift">
                      <ProductThumb icon={r.offer.icon} imageUrl={r.offer.image_url} category={r.offer.category} alt="" size="sm" />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium">{r.offer.name}</p>
                        <p className="truncate text-xs text-muted-foreground">
                          {r.same_shop ? "Also at this shop" : `${r.offer.shop.name} · ${formatDistance(r.offer.shop.distance_km)}`}
                          {r.confidence !== null && ` · ${Math.round(r.confidence * 100)}% of buyers`}
                        </p>
                      </div>
                      <span className="text-sm font-semibold tabular">{formatPrice(r.offer.price)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {/* reviews */}
          <section>
            <h2 className="text-xl font-semibold">What customers say about {shop.name}</h2>
            <div className="mt-4">
              <ReviewList reviews={p.reviews} empty="No reviews yet. Reviews come only from completed pickups and deliveries." />
            </div>
            {shop.rating_count > p.reviews.length && (
              <Link href={`/shops/${shop.slug}#reviews`} className="mt-2 inline-flex items-center gap-1 text-sm font-medium hover:underline">
                All {shop.rating_count} reviews <ArrowRight className="size-3.5" />
              </Link>
            )}
          </section>
        </div>

        {/* ---------------------------------------------------------- right: buy box */}
        <aside className="space-y-4 lg:sticky lg:top-20 lg:self-start">
          <div className="rounded-3xl border bg-card p-5 shadow-soft">
            <Price value={p.price} mrp={p.mrp} size="xl" />
            {insight?.statement && (
              <p className={cn("mt-2 inline-flex items-center gap-1.5 text-sm", (insight.deviation_pct ?? 0) < -3 ? "text-success-ink" : "text-muted-foreground")}>
                {(insight.deviation_pct ?? 0) < -3 ? <TrendingDown className="size-4" /> : (insight.deviation_pct ?? 0) > 3 ? <TrendingUp className="size-4" /> : null}
                {insight.statement}
              </p>
            )}
            <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-2">
              <StockPill status={p.stock_status} quantity={p.quantity} />
              <Freshness at={p.stock_updated_at} />
            </div>
            {p.sold_last_30d > 0 && <p className="mt-2 text-xs text-muted-foreground">{p.sold_last_30d} sold here in the last 30 days</p>}

            {p.my_reservation ? (
              <Link href={`/account/reservations/${p.my_reservation.id}`} className="mt-5 flex items-center justify-between rounded-2xl bg-brand-soft p-4 text-brand-ink">
                <span>
                  <span className="block text-sm font-semibold">You reserved this · {p.my_reservation.code}</span>
                  <StatusBadge status={p.my_reservation.status} kind="reservation" className="mt-1 bg-card" />
                </span>
                <ArrowRight className="size-4" />
              </Link>
            ) : (
              <div className="mt-5 space-y-2.5">
                <Button
                  size="lg"
                  className="h-12 w-full rounded-xl bg-brand text-base text-brand-foreground hover:bg-brand/90"
                  disabled={out || !shop.offers_pickup || !isCustomer}
                  onClick={() => requireCustomer(() => setReserveOpen(true))}
                >
                  <Footprints /> Reserve for pickup
                </Button>
                <Button
                  size="lg"
                  variant="outline"
                  className="h-12 w-full rounded-xl text-base"
                  disabled={out || !shop.offers_delivery || !isCustomer || (delivery !== null && !delivery.eligible)}
                  onClick={() => requireCustomer(() => setDeliveryOpen(true))}
                >
                  <Bike /> Request delivery
                </Button>
                <p className="text-center text-xs text-muted-foreground">
                  {!isCustomer
                    ? "Sign in with a customer account to reserve."
                    : out
                      ? "Out of stock here. Compare other shops below."
                      : !shop.offers_delivery
                        ? `Pickup only. Held ${shop.hold_minutes} min after the shop confirms.`
                        : delivery && !delivery.eligible
                          ? delivery.reason
                          : delivery
                            ? `Delivery ${delivery.delivery_fee ? formatPrice(delivery.delivery_fee) : "free"} · ${formatDistance(delivery.distance_km)} away · Cash on delivery`
                            : "Pay at the shop. No online payment."}
                </p>
              </div>
            )}
          </div>

          {/* shop box */}
          <div className="rounded-3xl border bg-card p-5">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <Link href={`/shops/${shop.slug}`} className="flex items-center gap-1 font-semibold hover:underline">
                  <span className="truncate">{shop.name}</span>
                  {shop.is_verified && <VerifiedMark />}
                </Link>
                <p className="mt-0.5 text-sm text-muted-foreground">{shop.address_line}</p>
              </div>
              <Rating value={shop.rating_avg} count={shop.rating_count} />
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-sm">
              <OpenBadge isOpen={shop.is_open} label={shop.hours_label} />
              {shop.distance_km !== null && (
                <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                  <MapPin className="size-3.5" /> <Distance km={shop.distance_km} /> · {travelHint(shop.distance_km)}
                </span>
              )}
            </div>
            <div className="mt-4 h-40 overflow-hidden rounded-2xl border">
              <ShopMap
                className="h-full"
                center={shop}
                zoom={15}
                fitToPoints={false}
                interactive={false}
                points={[{ id: shop.id, lat: shop.lat, lng: shop.lng, label: shop.name, title: shop.name }]}
                user={location?.source === "gps" ? location : null}
              />
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <Button asChild variant="outline" size="sm">
                <a href={`https://www.openstreetmap.org/directions?to=${shop.lat}%2C${shop.lng}`} target="_blank" rel="noreferrer">
                  <Navigation /> Directions
                </a>
              </Button>
              {shop.phone && (
                <Button asChild variant="outline" size="sm">
                  <a href={`tel:${shop.phone}`}><Phone /> Call shop</a>
                </Button>
              )}
            </div>
          </div>

          <div className="rounded-3xl border bg-card p-5">
            <p className="mb-3 text-sm font-semibold">Why you can trust this listing</p>
            <ShopTrust r={shop.reliability} />
          </div>
        </aside>
      </div>

      {/* mobile sticky buy bar */}
      {!p.my_reservation && isCustomer && !out && (
        <div className="fixed inset-x-0 bottom-[calc(3.9rem+env(safe-area-inset-bottom))] z-30 border-t bg-background/95 p-3 backdrop-blur lg:hidden">
          <div className="mx-auto flex max-w-md items-center gap-3">
            <div className="min-w-0">
              <p className="text-lg font-semibold tabular">{formatPrice(p.price)}</p>
              <p className="truncate text-xs text-muted-foreground">{p.quantity} in stock · {shop.name}</p>
            </div>
            <Button className="ml-auto h-11 rounded-xl bg-brand px-5 text-brand-foreground hover:bg-brand/90" onClick={() => requireCustomer(() => setReserveOpen(true))}>
              <Footprints /> Reserve
            </Button>
          </div>
        </div>
      )}

      <ReserveDialog product={p} open={reserveOpen} onOpenChange={setReserveOpen} />
      {shop.offers_delivery && <DeliveryDialog product={p} open={deliveryOpen} onOpenChange={setDeliveryOpen} />}
    </div>
  );
}

function ProductSkeleton() {
  return (
    <div className="mx-auto grid max-w-7xl gap-10 px-4 pt-10 md:px-6 lg:grid-cols-[1fr_420px]">
      <div className="grid gap-6 sm:grid-cols-[280px_1fr]">
        <Skeleton className="aspect-square rounded-3xl" />
        <div className="space-y-3">
          <Skeleton className="h-4 w-24" />
          <Skeleton className="h-8 w-3/4" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
        </div>
      </div>
      <Skeleton className="h-80 rounded-3xl" />
    </div>
  );
}
