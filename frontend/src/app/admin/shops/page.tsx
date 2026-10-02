"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Search } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { Freshness, Rating } from "@/components/common/indicators";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { PageTitle } from "@/components/dashboard/dashboard-shell";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useDebounce } from "@/hooks/use-debounce";
import { api } from "@/lib/api";
import type { ShopBrief } from "@/lib/types";

type AdminShop = ShopBrief & { is_active: boolean; owner: string; owner_email: string; listings: number; created_at: string };

export default function AdminShopsPage() {
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const q = useDebounce(text, 250);
  const shops = useQuery({ queryKey: ["admin", "shops", q], queryFn: () => api.get<AdminShop[]>("/admin/shops", { q }), placeholderData: keepPreviousData });
  const update = useMutation({
    mutationFn: ({ id, body }: { id: number; body: { is_verified?: boolean; is_active?: boolean } }) => api.patch(`/admin/shops/${id}`, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin"] });
      toast.success("Shop updated");
    },
  });

  return (
    <>
      <PageTitle title="Shops" description="Verify shops after an in-person check. Deactivating hides a shop from search without deleting anything." />
      <div className="relative mb-4 max-w-sm">
        <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Search shops or areas" className="h-9 pl-9" />
      </div>
      {shops.isError ? (
        <ErrorState error={shops.error} onRetry={() => shops.refetch()} />
      ) : !shops.data ? (
        <ListSkeleton />
      ) : (
        <div className="overflow-x-auto rounded-2xl border bg-card">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Shop</TableHead>
                <TableHead className="hidden md:table-cell">Owner</TableHead>
                <TableHead className="text-right">Listings</TableHead>
                <TableHead className="hidden lg:table-cell">Rating</TableHead>
                <TableHead className="hidden lg:table-cell">Stock updated</TableHead>
                <TableHead>Verified</TableHead>
                <TableHead>Active</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {shops.data.map((s) => (
                <TableRow key={s.id}>
                  <TableCell>
                    <Link href={`/shops/${s.slug}`} className="font-medium hover:underline">{s.name}</Link>
                    <p className="text-xs text-muted-foreground">{s.locality}</p>
                  </TableCell>
                  <TableCell className="hidden md:table-cell">
                    <p>{s.owner}</p>
                    <p className="text-xs text-muted-foreground">{s.owner_email}</p>
                  </TableCell>
                  <TableCell className="text-right tabular">{s.listings}</TableCell>
                  <TableCell className="hidden lg:table-cell"><Rating value={s.rating_avg} count={s.rating_count} /></TableCell>
                  <TableCell className="hidden lg:table-cell"><Freshness at={s.inventory_updated_at} prefix="" /></TableCell>
                  <TableCell>
                    <Switch checked={s.is_verified} onCheckedChange={(v) => update.mutate({ id: s.id, body: { is_verified: v } })} aria-label={`Verified: ${s.name}`} />
                  </TableCell>
                  <TableCell>
                    <Switch checked={s.is_active} onCheckedChange={(v) => update.mutate({ id: s.id, body: { is_active: v } })} aria-label={`Active: ${s.name}`} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </>
  );
}
