"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import {
  ArrowUpDown,
  Bike,
  List,
  Loader2,
  Map as MapIcon,
  PackageSearch,
  SlidersHorizontal,
  Sparkles,
  Store,
  X,
} from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import { AppIcon } from "@/components/common/app-icon";
import { Distance, Rating } from "@/components/common/indicators";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { ShopMap } from "@/components/map/shop-map";
import { ResultCard } from "@/components/search/result-card";
import { LocationPicker } from "@/components/site/location-picker";
import { SearchBox } from "@/components/site/search-box";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetFooter, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useMeta } from "@/hooks/use-session";
import { api } from "@/lib/api";
import { formatPrice, pluralize } from "@/lib/format";
import { useLocation } from "@/lib/location";
import type { MapPin, SearchResponse } from "@/lib/types";
import { cn } from "@/lib/utils";

const SORTS = [
  { value: "relevance", label: "Best match" },
  { value: "distance", label: "Nearest first" },
  { value: "price_asc", label: "Price: low to high" },
  { value: "price_desc", label: "Price: high to low" },
];

export function SearchView() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const { data: meta } = useMeta();
  const { location, radiusKm, setRadiusKm, ready } = useLocation();
  const [mobileMap, setMobileMap] = useState(false);
  const [hoverShops, setHoverShops] = useState<number[] | null>(null);
  const [selectedShop, setSelectedShop] = useState<number | null>(null);

  const q = params.get("q") ?? "";
  const category = params.get("category") ?? "";
  const sort = params.get("sort") ?? "relevance";
  const inStock = params.get("stock") === "1";
  const fulfillment = params.get("fulfillment") ?? "";
  const minPrice = params.get("min") ?? "";
  const maxPrice = params.get("max") ?? "";

  function setParam(updates: Record<string, string | null>) {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(updates)) {
      if (v === null || v === "") next.delete(k);
      else next.set(k, v);
    }
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  }

  const query = useInfiniteQuery({
    queryKey: ["search", q, category, sort, inStock, fulfillment, minPrice, maxPrice, location?.lat, location?.lng, radiusKm],
    queryFn: ({ pageParam }) =>
      api.get<SearchResponse>("/search", {
        q,
        category,
        sort,
        in_stock_only: inStock || undefined,
        fulfillment: fulfillment || undefined,
        min_price: minPrice || undefined,
        max_price: maxPrice || undefined,
        lat: location!.lat,
        lng: location!.lng,
        radius_km: radiusKm,
        page: pageParam,
        page_size: 20,
      }),
    initialPageParam: 1,
    getNextPageParam: (last) => (last.has_more ? last.page + 1 : undefined),
    enabled: ready,
    placeholderData: (prev) => prev,
  });

  const first = query.data?.pages[0];
  const groups = useMemo(() => query.data?.pages.flatMap((p) => p.groups) ?? [], [query.data]);
  const pins: MapPin[] = useMemo(() => first?.shops ?? [], [first]);
  const points = useMemo(
    () =>
      pins.map((s) => ({
        id: s.id,
        lat: s.lat,
        lng: s.lng,
        label: s.min_price !== null ? formatPrice(s.min_price) : "Out of stock",
        title: `${s.name}, ${s.in_stock_count} matching items in stock`,
        muted: s.in_stock_count === 0,
      })),
    [pins],
  );
  const selected = pins.find((s) => s.id === selectedShop);
  const catName = meta?.categories.find((c) => c.slug === category)?.name;
  const activeFilters = [inStock, !!fulfillment, !!minPrice || !!maxPrice].filter(Boolean).length;
  const heading = q ? `"${first?.corrected_from ? first.normalized_query : q}"` : catName ?? "Everything nearby";

  const filtersBody = (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4">
        <Label htmlFor="instock" className="flex flex-col items-start gap-0.5">
          <span>In stock only</span>
          <span className="text-xs font-normal text-muted-foreground">Hide items shops have run out of</span>
        </Label>
        <Switch id="instock" checked={inStock} onCheckedChange={(v) => setParam({ stock: v ? "1" : null })} />
      </div>
      <div className="space-y-2">
        <Label>How you want it</Label>
        <ToggleGroup
          type="single"
          variant="outline"
          value={fulfillment || "any"}
          onValueChange={(v) => setParam({ fulfillment: v === "any" || !v ? null : v })}
          className="w-full"
        >
          <ToggleGroupItem value="any" className="flex-1">Any</ToggleGroupItem>
          <ToggleGroupItem value="pickup" className="flex-1">Pickup</ToggleGroupItem>
          <ToggleGroupItem value="delivery" className="flex-1">Delivery</ToggleGroupItem>
        </ToggleGroup>
      </div>
      <div className="space-y-2">
        <Label>Price range (Rs)</Label>
        <div className="flex items-center gap-2">
          <Input inputMode="numeric" placeholder="Min" defaultValue={minPrice} onBlur={(e) => setParam({ min: e.target.value.replace(/\D/g, "") })} aria-label="Minimum price" />
          <span className="text-muted-foreground">to</span>
          <Input inputMode="numeric" placeholder="Max" defaultValue={maxPrice} onBlur={(e) => setParam({ max: e.target.value.replace(/\D/g, "") })} aria-label="Maximum price" />
        </div>
      </div>
    </div>
  );

  return (
    <div className="mx-auto max-w-[1440px] lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(380px,44%)]">
      {/* ------------------------------------------------------------ results column */}
      <div className={cn("min-w-0 px-4 pt-4 pb-10 md:px-6", mobileMap && "max-lg:hidden")}>
        <div className="space-y-3 md:hidden">
          <SearchBox />
          <LocationPicker className="max-w-full" />
        </div>

        {/* category chips */}
        <div className="-mx-4 mt-4 flex gap-2 overflow-x-auto px-4 pb-1 scrollbar-none md:mx-0 md:mt-1 md:px-0">
          <Chip active={!category} onClick={() => setParam({ category: null })}>All</Chip>
          {meta?.categories.map((c) => (
            <Chip key={c.slug} active={category === c.slug} onClick={() => setParam({ category: category === c.slug ? null : c.slug })}>
              <AppIcon name={c.icon} className="size-3.5" />
              {c.name}
              {q && first?.category_counts[c.slug] ? (
                <span className="text-muted-foreground tabular">{first.category_counts[c.slug]}</span>
              ) : null}
            </Chip>
          ))}
        </div>

        {/* summary + controls */}
        <div className="mt-5 flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-semibold">{heading}</h1>
            <p className="mt-0.5 text-sm text-muted-foreground" aria-live="polite">
              {query.isLoading || !first ? (
                "Checking shelves nearby..."
              ) : (
                <>
                  {pluralize(first.total, "item")} at {pluralize(first.shops.length, "shop")} within {radiusKm} km
                  {location && <> of {location.label}</>}
                </>
              )}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Select value={sort} onValueChange={(v) => setParam({ sort: v === "relevance" ? null : v })}>
              <SelectTrigger className="h-9 w-auto gap-2 rounded-full" aria-label="Sort results">
                <ArrowUpDown className="size-3.5" />
                <SelectValue />
              </SelectTrigger>
              <SelectContent align="end">
                {SORTS.map((s) => (
                  <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Sheet>
              <SheetTrigger asChild>
                <Button variant="outline" className="h-9 rounded-full">
                  <SlidersHorizontal /> Filters
                  {activeFilters > 0 && (
                    <span className="grid size-5 place-items-center rounded-full bg-primary text-[11px] text-primary-foreground tabular">{activeFilters}</span>
                  )}
                </Button>
              </SheetTrigger>
              <SheetContent className="w-full sm:max-w-sm">
                <SheetHeader>
                  <SheetTitle>Filters</SheetTitle>
                </SheetHeader>
                <div className="px-4">{filtersBody}</div>
                <SheetFooter>
                  <Button variant="ghost" onClick={() => setParam({ stock: null, fulfillment: null, min: null, max: null })}>
                    Clear all
                  </Button>
                </SheetFooter>
              </SheetContent>
            </Sheet>
          </div>
        </div>

        {/* AI hint / corrections */}
        <AnimatePresence>
          {first?.corrected_from && (
            <motion.p initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} className="mt-3 text-sm">
              Showing results for <span className="font-medium">{first.normalized_query}</span>. No matches for &ldquo;{first.corrected_from}&rdquo;.
            </motion.p>
          )}
          {first?.did_you_mean && (
            <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-3 text-sm">
              Did you mean{" "}
              <Link href={`/search?q=${encodeURIComponent(first.did_you_mean)}`} className="font-medium text-brand-ink underline underline-offset-4">
                {first.did_you_mean}
              </Link>
              ?
            </motion.p>
          )}
        </AnimatePresence>
        {q && first && first.total > 0 && !first.corrected_from && (
          <p className="mt-3 inline-flex items-center gap-1.5 text-xs text-muted-foreground">
            <Sparkles className="size-3.5 text-brand" /> Matched by meaning and keywords
            {first.expanded_terms.length > 0 && <>, also looked for {first.expanded_terms.slice(0, 3).join(", ")}</>}
          </p>
        )}

        {/* results */}
        <div className="mt-5">
          {query.isError ? (
            <ErrorState error={query.error} onRetry={() => query.refetch()} />
          ) : query.isLoading || !first ? (
            <ListSkeleton rows={5} />
          ) : groups.length === 0 ? (
            <EmptyState
              icon={PackageSearch}
              title={first.shops_in_radius === 0 ? "No shops in this radius yet" : `Nothing matching within ${radiusKm} km`}
              description={
                first.shops_in_radius === 0
                  ? "Try a wider radius or a different area."
                  : "Shops nearby don't list this yet. Try a wider radius, fewer filters, or a simpler word."
              }
              action={
                <>
                  {radiusKm < 15 && (
                    <Button onClick={() => setRadiusKm(Math.min(15, radiusKm + 5))}>Expand to {Math.min(15, radiusKm + 5)} km</Button>
                  )}
                  {activeFilters > 0 && (
                    <Button variant="outline" onClick={() => setParam({ stock: null, fulfillment: null, min: null, max: null })}>
                      Clear filters
                    </Button>
                  )}
                </>
              }
            />
          ) : (
            <div className={cn("space-y-3 transition-opacity", query.isFetching && !query.isFetchingNextPage && "opacity-60")}>
              {groups.map((g, i) => (
                <ResultCard
                  key={g.key}
                  group={g}
                  index={i}
                  highlighted={!!selectedShop && g.offers.some((o) => o.shop.id === selectedShop)}
                  onHover={setHoverShops}
                />
              ))}
              {query.hasNextPage && (
                <Button variant="outline" className="w-full" onClick={() => query.fetchNextPage()} disabled={query.isFetchingNextPage}>
                  {query.isFetchingNextPage ? <Loader2 className="animate-spin" /> : null} Show more results
                </Button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ------------------------------------------------------------ map column */}
      <div
        className={cn(
          "lg:sticky lg:top-16 lg:block lg:h-[calc(100dvh-4rem)] lg:p-3 lg:pl-0",
          mobileMap ? "fixed inset-x-0 top-16 bottom-[calc(3.9rem+env(safe-area-inset-bottom))] z-30 block" : "hidden",
        )}
      >
        {location && (
          <div className="relative h-full overflow-hidden lg:rounded-3xl lg:border">
            <ShopMap
              className="h-full"
              center={location}
              user={location.source === "gps" ? location : null}
              radiusKm={radiusKm}
              points={points}
              highlighted={hoverShops}
              selected={selectedShop}
              onSelect={(id) => setSelectedShop(id === selectedShop ? null : id)}
            />
            <AnimatePresence>
              {selected && (
                <motion.div
                  initial={{ opacity: 0, y: 16 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: 16 }}
                  className="absolute inset-x-3 bottom-3 rounded-2xl border bg-card p-4 shadow-lift"
                >
                  <button onClick={() => setSelectedShop(null)} className="absolute top-3 right-3 rounded-full p-1 text-muted-foreground hover:bg-muted" aria-label="Close">
                    <X className="size-4" />
                  </button>
                  <div className="flex items-center gap-2 pr-8">
                    <Store className="size-4 text-muted-foreground" />
                    <p className="truncate font-semibold">{selected.name}</p>
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-x-3 text-sm text-muted-foreground">
                    <span>{selected.locality}</span>
                    <Distance km={selected.distance_km} className="text-sm" />
                    <Rating value={selected.rating_avg} count={selected.rating_count} />
                    {selected.offers_delivery && (
                      <span className="inline-flex items-center gap-1 text-xs"><Bike className="size-3.5" /> Delivers</span>
                    )}
                  </div>
                  <p className="mt-2 text-sm">
                    {selected.in_stock_count > 0
                      ? `${pluralize(selected.in_stock_count, "matching item")} in stock, from ${formatPrice(selected.min_price)}`
                      : "Has matching items, but they're out of stock"}
                  </p>
                  <Button asChild size="sm" variant="outline" className="mt-3">
                    <Link href={`/shops/${selected.slug}${q ? `?q=${encodeURIComponent(q)}` : ""}`}>Open shop</Link>
                  </Button>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}
      </div>

      {/* mobile list/map toggle */}
      <Button
        onClick={() => setMobileMap((v) => !v)}
        className="fixed bottom-[calc(4.6rem+env(safe-area-inset-bottom))] left-1/2 z-30 h-11 -translate-x-1/2 rounded-full px-5 shadow-lift lg:hidden"
      >
        {mobileMap ? <><List /> List</> : <><MapIcon /> Map</>}
      </Button>
    </div>
  );
}

function Chip({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm whitespace-nowrap transition-colors",
        active ? "border-primary bg-primary text-primary-foreground" : "bg-card hover:bg-accent",
      )}
    >
      {children}
    </button>
  );
}
