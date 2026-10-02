import { BadgeCheck, Star } from "lucide-react";

import { timeAgo } from "@/lib/format";
import type { Review } from "@/lib/types";
import { cn } from "@/lib/utils";

export function Stars({ value, className }: { value: number; className?: string }) {
  return (
    <span className={cn("inline-flex", className)} aria-label={`${value} out of 5 stars`}>
      {[1, 2, 3, 4, 5].map((i) => (
        <Star key={i} className={cn("size-3.5", i <= value ? "fill-warning text-warning" : "text-muted-foreground/30")} />
      ))}
    </span>
  );
}

export function ReviewList({ reviews, empty = "No reviews yet." }: { reviews: Review[]; empty?: string }) {
  if (!reviews.length) return <p className="text-sm text-muted-foreground">{empty}</p>;
  return (
    <ul className="divide-y">
      {reviews.map((r) => (
        <li key={r.id} className="py-4 first:pt-0">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Stars value={r.rating} />
              <span className="text-sm font-medium">{r.customer_name}</span>
            </div>
            <span className="text-xs text-muted-foreground" suppressHydrationWarning>{timeAgo(r.created_at)}</span>
          </div>
          {r.comment && <p className="mt-1.5 text-sm">{r.comment}</p>}
          <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1"><BadgeCheck className="size-3.5 text-success" /> Verified {r.source}</span>
            {r.product_name && <span className="truncate">{r.product_name}</span>}
            {r.accuracy_rating && <span>Item accuracy {r.accuracy_rating}/5</span>}
            {r.delivery_rating && <span>Delivery {r.delivery_rating}/5</span>}
          </p>
        </li>
      ))}
    </ul>
  );
}
