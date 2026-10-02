"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Scale, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { ProductThumb } from "@/components/common/product-thumb";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { PageTitle } from "@/components/dashboard/dashboard-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { formatPrice, timeAgo } from "@/lib/format";
import type { PriceFlag } from "@/lib/types";

export default function AnomaliesPage() {
  const qc = useQueryClient();
  const [status, setStatus] = useState<"open" | "reviewed" | "dismissed">("open");
  const q = useQuery({ queryKey: ["admin", "anomalies", status], queryFn: () => api.get<PriceFlag[]>("/admin/anomalies", { status }) });
  const review = useMutation({
    mutationFn: ({ id, s }: { id: number; s: "reviewed" | "dismissed" }) => api.post(`/admin/anomalies/${id}`, { status: s }),
    onSuccess: (_d, v) => {
      qc.invalidateQueries({ queryKey: ["admin"] });
      toast.success(v.s === "reviewed" ? "Marked as reviewed" : "Dismissed. It won't be flagged again at this price.");
    },
  });

  return (
    <>
      <PageTitle
        title="Price review"
        description="Isolation Forest flags listings priced far from other shops selling the same item. Flags never hide a listing; a person decides."
        action={
          <Tabs value={status} onValueChange={(v) => setStatus(v as typeof status)}>
            <TabsList>
              <TabsTrigger value="open">Open</TabsTrigger>
              <TabsTrigger value="reviewed">Reviewed</TabsTrigger>
              <TabsTrigger value="dismissed">Dismissed</TabsTrigger>
            </TabsList>
          </Tabs>
        }
      />
      {q.isError ? (
        <ErrorState error={q.error} onRetry={() => q.refetch()} />
      ) : !q.data ? (
        <ListSkeleton />
      ) : !q.data.length ? (
        <EmptyState icon={Scale} title={status === "open" ? "Nothing to review" : `No ${status} flags`} description="New flags appear after the model retrains." />
      ) : (
        <ul className="divide-y rounded-2xl border bg-card">
          {q.data.map((f) => (
            <li key={f.id} className="flex flex-wrap items-center gap-4 p-4 sm:flex-nowrap">
              <ProductThumb icon={f.product.icon} category={f.product.category} imageUrl={f.product.image_url} alt="" size="sm" />
              <div className="min-w-0 flex-1 basis-60">
                <Link href={`/product/${f.product.id}`} className="block truncate font-medium hover:underline">{f.product.name}</Link>
                <p className="text-sm text-muted-foreground">
                  <Link href={`/shops/${f.shop.slug}`} className="hover:underline">{f.shop.name}</Link>, {f.shop.locality} · flagged {timeAgo(f.created_at)}
                </p>
              </div>
              <div className="text-right text-sm tabular">
                <p className="font-semibold">{formatPrice(f.price)}</p>
                <p className="text-xs text-muted-foreground">typical {formatPrice(f.reference_price)} ({f.peer_count} shops)</p>
              </div>
              <Badge className={f.direction === "high" ? "bg-warning-soft text-warning-ink" : "bg-info-soft text-info-ink"}>
                {f.deviation_pct > 0 ? "+" : ""}{f.deviation_pct}% · score {f.score.toFixed(2)}
              </Badge>
              {status === "open" && (
                <div className="flex gap-1">
                  <Button size="sm" variant="outline" onClick={() => review.mutate({ id: f.id, s: "reviewed" })} disabled={review.isPending}><Check /> Reviewed</Button>
                  <Button size="sm" variant="ghost" onClick={() => review.mutate({ id: f.id, s: "dismissed" })} disabled={review.isPending}><X /> Dismiss</Button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
