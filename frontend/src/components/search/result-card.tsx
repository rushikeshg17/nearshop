"use client";

import { Bike, ChevronRight, Footprints, Store } from "lucide-react";
import { motion } from "motion/react";
import Link from "next/link";

import { Distance, Freshness, Rating, StockPill } from "@/components/common/indicators";
import { ProductThumb } from "@/components/common/product-thumb";
import { formatDistance, formatPrice, travelHint } from "@/lib/format";
import type { ResultGroup } from "@/lib/types";
import { cn } from "@/lib/utils";

export function ResultCard({
  group,
  index = 0,
  highlighted,
  onHover,
}: {
  group: ResultGroup;
  index?: number;
  highlighted?: boolean;
  onHover?: (shopIds: number[] | null) => void;
}) {
  const best = group.best_offer;
  const others = group.offers.filter((o) => o.id !== best.id).slice(0, 3);
  const outOfStock = group.in_stock_count === 0;

  return (
    <motion.article
      layout="position"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.32, delay: Math.min(index, 8) * 0.035, ease: [0.22, 1, 0.36, 1] }}
      onMouseEnter={() => onHover?.(group.offers.map((o) => o.shop.id))}
      onMouseLeave={() => onHover?.(null)}
      className={cn(
        "group relative rounded-2xl border bg-card transition-[box-shadow,border-color] duration-200 hover:border-foreground/15 hover:shadow-lift",
        highlighted && "border-brand/40 shadow-lift",
        outOfStock && "opacity-80",
      )}
    >
      <Link href={`/product/${best.id}`} className="flex gap-4 p-4 outline-none" aria-label={`${group.name}, from ${formatPrice(group.min_price)}`}>
        <ProductThumb icon={group.icon} imageUrl={group.image_url} category={group.category} alt="" size="lg" className="max-sm:size-20" />
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              {group.brand && <p className="text-xs font-medium tracking-wide text-muted-foreground uppercase">{group.brand}</p>}
              <h3 className="line-clamp-2 leading-snug font-semibold">{group.name}</h3>
            </div>
            <div className="shrink-0 text-right">
              <p className="text-lg font-semibold tracking-tight tabular">{formatPrice(group.min_price)}</p>
              {group.max_price > group.min_price && (
                <p className="text-xs text-muted-foreground tabular">up to {formatPrice(group.max_price)}</p>
              )}
            </div>
          </div>

          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
            <StockPill status={best.stock_status} quantity={best.quantity} />
            <Freshness at={best.stock_updated_at} />
          </div>

          <div className="mt-3 flex items-center gap-2 text-sm">
            <Store className="size-4 shrink-0 text-muted-foreground" />
            <span className="truncate font-medium">{best.shop.name}</span>
            <span className="shrink-0 text-muted-foreground">·</span>
            <Distance km={best.shop.distance_km} className="shrink-0 text-sm" />
            <span className="hidden shrink-0 text-xs text-muted-foreground sm:inline">({travelHint(best.shop.distance_km)})</span>
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <Rating value={best.shop.rating_avg} count={best.shop.rating_count} />
            {best.shop.offers_pickup && (
              <span className="inline-flex items-center gap-1">
                <Footprints className="size-3.5" /> Pickup
              </span>
            )}
            {best.shop.offers_delivery && (
              <span className="inline-flex items-center gap-1">
                <Bike className="size-3.5" /> Delivery
              </span>
            )}
          </div>
        </div>
      </Link>

      {group.shop_count > 1 && (
        <div className="border-t px-4 py-2.5">
          <p className="mb-1.5 text-xs font-medium text-muted-foreground">
            {group.shop_count} shops nearby have this
            {group.in_stock_count < group.shop_count && ` · ${group.in_stock_count} in stock`}
          </p>
          <ul className="flex flex-wrap gap-1.5">
            {others.map((o) => (
              <li key={o.id}>
                <Link
                  href={`/product/${o.id}`}
                  className={cn(
                    "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs transition-colors hover:bg-accent",
                    o.quantity <= 0 && "text-muted-foreground line-through decoration-muted-foreground/40",
                  )}
                >
                  <span className="max-w-36 truncate">{o.shop.name}</span>
                  <span className="font-medium tabular">{formatPrice(o.price)}</span>
                  <span className="text-muted-foreground tabular">{formatDistance(o.shop.distance_km)}</span>
                </Link>
              </li>
            ))}
            {group.shop_count > 4 && (
              <li>
                <Link href={`/product/${best.id}#compare`} className="inline-flex items-center gap-0.5 rounded-full px-2 py-1 text-xs font-medium hover:bg-accent">
                  Compare all <ChevronRight className="size-3" />
                </Link>
              </li>
            )}
          </ul>
        </div>
      )}
    </motion.article>
  );
}
