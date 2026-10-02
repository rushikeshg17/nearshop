"use client";

import { useQuery } from "@tanstack/react-query";
import { Star } from "lucide-react";

import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { PageTitle } from "@/components/dashboard/dashboard-shell";
import { ReviewList } from "@/components/shop/review-list";
import { api } from "@/lib/api";
import type { Review } from "@/lib/types";

export default function OwnerReviewsPage() {
  const q = useQuery({ queryKey: ["owner", "reviews"], queryFn: () => api.get<Review[]>("/owner/reviews") });
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  if (!q.data) return <ListSkeleton />;
  const reviews = q.data;
  const avg = reviews.length ? reviews.reduce((s, r) => s + r.rating, 0) / reviews.length : 0;
  const dist = [5, 4, 3, 2, 1].map((n) => ({ n, c: reviews.filter((r) => r.rating === n).length }));

  return (
    <>
      <PageTitle title="Reviews" description="Only customers who completed a pickup or delivery can review, once per purchase." />
      {!reviews.length ? (
        <EmptyState icon={Star} title="No reviews yet" description="After a pickup or delivery is completed, the customer is invited to rate it." />
      ) : (
        <div className="grid gap-6 lg:grid-cols-[260px_1fr]">
          <div className="h-fit rounded-2xl border bg-card p-5">
            <p className="font-heading text-4xl font-semibold tabular">{avg.toFixed(1)}</p>
            <p className="text-sm text-muted-foreground">from the latest {reviews.length} reviews</p>
            <ul className="mt-4 space-y-1.5">
              {dist.map(({ n, c }) => (
                <li key={n} className="flex items-center gap-2 text-xs">
                  <span className="w-3 tabular">{n}</span>
                  <Star className="size-3 fill-warning text-warning" />
                  <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
                    <span className="block h-full rounded-full bg-warning" style={{ width: `${(c / reviews.length) * 100}%` }} />
                  </span>
                  <span className="w-6 text-right text-muted-foreground tabular">{c}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="rounded-2xl border bg-card p-5">
            <ReviewList reviews={reviews} />
          </div>
        </div>
      )}
    </>
  );
}
