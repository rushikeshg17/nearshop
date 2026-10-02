"use client";

import { useQuery } from "@tanstack/react-query";
import { Search, Store } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { AppIcon } from "@/components/common/app-icon";
import { EmptyState, ErrorState } from "@/components/common/states";
import { ShopMap } from "@/components/map/shop-map";
import { ShopCard } from "@/components/shop/shop-card";
import { LocationPicker } from "@/components/site/location-picker";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useDebounce } from "@/hooks/use-debounce";
import { useMeta } from "@/hooks/use-session";
import { api } from "@/lib/api";
import { useLocation } from "@/lib/location";
import type { ShopBrief } from "@/lib/types";
import { cn } from "@/lib/utils";

export function ShopsView() {
  const router = useRouter();
  const { data: meta } = useMeta();
  const { location, radiusKm, ready } = useLocation();
  const [category, setCategory] = useState<string | null>(null);
  const [sort, setSort] = useState("distance");
  const [text, setText] = useState("");
  const [hover, setHover] = useState<number | null>(null);
  const q = useDebounce(text, 250);

  const shops = useQuery({
    queryKey: ["shops", "list", location?.lat, location?.lng, radiusKm, category, sort, q],
    queryFn: () =>
      api.get<{ shops: ShopBrief[] }>("/shops", { lat: location!.lat, lng: location!.lng, radius_km: Math.max(radiusKm, 3), category, sort, q }),
    enabled: ready,
    placeholderData: (p) => p,
  });
  const list = useMemo(() => shops.data?.shops ?? [], [shops.data]);
  const points = useMemo(
    () => list.map((s) => ({ id: s.id, lat: s.lat, lng: s.lng, label: s.name.length > 18 ? `${s.name.slice(0, 17)}…` : s.name, title: s.name, muted: s.is_open === false })),
    [list],
  );

  return (
    <div className="mx-auto max-w-[1440px] lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(380px,42%)]">
      <div className="min-w-0 px-4 pt-6 pb-10 md:px-6">
        <h1 className="text-3xl font-semibold">Shops near you</h1>
        <p className="mt-1 text-muted-foreground">Local shops that keep their stock online. Freshness shows when they last counted.</p>

        <div className="mt-5 flex flex-wrap items-center gap-2">
          <LocationPicker />
          <div className="relative min-w-48 flex-1">
            <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Shop name or area" className="h-9 rounded-full pl-9" />
          </div>
          <Select value={sort} onValueChange={setSort}>
            <SelectTrigger className="h-9 w-44 rounded-full"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="distance">Nearest first</SelectItem>
              <SelectItem value="rating">Highest rated</SelectItem>
              <SelectItem value="fresh">Freshest stock</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <div className="-mx-4 mt-3 flex gap-2 overflow-x-auto px-4 pb-1 scrollbar-none md:mx-0 md:px-0">
          <button onClick={() => setCategory(null)} className={cn("shrink-0 rounded-full border px-3 py-1.5 text-sm", !category ? "border-primary bg-primary text-primary-foreground" : "bg-card hover:bg-accent")}>All</button>
          {meta?.categories.map((c) => (
            <button key={c.slug} onClick={() => setCategory(category === c.slug ? null : c.slug)}
              className={cn("inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm", category === c.slug ? "border-primary bg-primary text-primary-foreground" : "bg-card hover:bg-accent")}>
              <AppIcon name={c.icon} className="size-3.5" /> {c.name}
            </button>
          ))}
        </div>

        <div className="mt-6">
          {shops.isError ? (
            <ErrorState error={shops.error} onRetry={() => shops.refetch()} />
          ) : !shops.data ? (
            <div className="grid gap-3 sm:grid-cols-2">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-44 rounded-2xl" />)}</div>
          ) : list.length === 0 ? (
            <EmptyState icon={Store} title="No shops match" description="Try a wider radius or another category." />
          ) : (
            <>
              <p className="mb-3 text-sm text-muted-foreground">{list.length} shops within {Math.max(radiusKm, 3)} km</p>
              <div className="grid gap-3 sm:grid-cols-2">
                {list.map((s) => (
                  <div key={s.id} onMouseEnter={() => setHover(s.id)} onMouseLeave={() => setHover(null)}>
                    <ShopCard shop={s} categories={meta?.categories} className="h-full" />
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      </div>
      <div className="hidden lg:sticky lg:top-16 lg:block lg:h-[calc(100dvh-4rem)] lg:p-3 lg:pl-0">
        {location && (
          <div className="h-full overflow-hidden rounded-3xl border">
            <ShopMap className="h-full" center={location} radiusKm={Math.max(radiusKm, 3)} points={points} selected={hover}
              user={location.source === "gps" ? location : null}
              onSelect={(id) => {
                const s = list.find((x) => x.id === id);
                if (s) router.push(`/shops/${s.slug}`);
              }} />
          </div>
        )}
      </div>
    </div>
  );
}
