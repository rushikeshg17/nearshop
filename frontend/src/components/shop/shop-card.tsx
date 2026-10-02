import { Bike, Store } from "lucide-react";
import Link from "next/link";

import { AppIcon } from "@/components/common/app-icon";
import { Distance, Freshness, OpenBadge, Rating, VerifiedMark } from "@/components/common/indicators";
import type { Category, ShopBrief } from "@/lib/types";
import { cn } from "@/lib/utils";

export function ShopAvatar({ shop, categories, className }: { shop: ShopBrief; categories?: Category[]; className?: string }) {
  const cat = categories?.find((c) => c.slug === shop.categories[0]);
  const hue = cat?.color_hue ?? 40;
  if (shop.image_url) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={shop.image_url} alt="" className={cn("size-12 shrink-0 rounded-xl object-cover", className)} />;
  }
  return (
    <div
      className={cn("grid size-12 shrink-0 place-items-center rounded-xl text-lg font-semibold font-heading", className)}
      style={{
        background: `light-dark(oklch(0.94 0.035 ${hue}), oklch(0.3 0.04 ${hue}))`,
        color: `light-dark(oklch(0.45 0.12 ${hue}), oklch(0.85 0.08 ${hue}))`,
      }}
      aria-hidden
    >
      {cat ? <AppIcon name={cat.icon} className="size-5" /> : <Store className="size-5" />}
    </div>
  );
}

export function ShopCard({ shop, categories, className }: { shop: ShopBrief; categories?: Category[]; className?: string }) {
  const catNames = shop.categories
    .map((s) => categories?.find((c) => c.slug === s)?.name)
    .filter(Boolean)
    .join(" · ");
  return (
    <Link
      href={`/shops/${shop.slug}`}
      className={cn(
        "group flex flex-col gap-3 rounded-2xl border bg-card p-4 transition-[box-shadow,transform,border-color] duration-200 hover:-translate-y-0.5 hover:border-foreground/15 hover:shadow-lift",
        className,
      )}
    >
      <div className="flex items-start gap-3">
        <ShopAvatar shop={shop} categories={categories} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-1">
            <p className="truncate font-semibold">{shop.name}</p>
            {shop.is_verified && <VerifiedMark />}
          </div>
          <p className="truncate text-xs text-muted-foreground">
            {shop.locality}
            {shop.distance_km !== null && (
              <>
                {" · "}
                <Distance km={shop.distance_km} />
              </>
            )}
          </p>
        </div>
      </div>
      {catNames && <p className="truncate text-xs text-muted-foreground">{catNames}</p>}
      <div className="mt-auto flex flex-wrap items-center gap-x-3 gap-y-1">
        <Rating value={shop.rating_avg} count={shop.rating_count} />
        <OpenBadge isOpen={shop.is_open} label={shop.is_open ? "Open" : "Closed"} />
        {shop.offers_delivery && (
          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
            <Bike className="size-3.5" /> Delivers
          </span>
        )}
      </div>
      <Freshness at={shop.inventory_updated_at} prefix="Stock updated" />
    </Link>
  );
}
