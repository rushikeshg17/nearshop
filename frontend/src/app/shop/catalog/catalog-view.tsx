"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, PartyPopper, Search } from "lucide-react";
import { AnimatePresence, motion } from "motion/react";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { AppIcon } from "@/components/common/app-icon";
import { ProductThumb } from "@/components/common/product-thumb";
import { ErrorState, ListSkeleton } from "@/components/common/states";
import { PageTitle } from "@/components/dashboard/dashboard-shell";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { useDebounce } from "@/hooks/use-debounce";
import { useMeta } from "@/hooks/use-session";
import { api } from "@/lib/api";
import { formatPrice } from "@/lib/format";
import type { CatalogEntry } from "@/lib/types";
import { cn } from "@/lib/utils";

type Picked = Record<number, { price: string; quantity: string }>;

export function CatalogView() {
  const router = useRouter();
  const params = useSearchParams();
  const qc = useQueryClient();
  const { data: meta } = useMeta();
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<string | null>(null);
  const [picked, setPicked] = useState<Picked>({});
  const q = useDebounce(search, 250);
  const welcome = params.get("welcome") === "1";

  const list = useQuery({
    queryKey: ["owner", "catalog", q, category],
    queryFn: () => api.get<{ items: CatalogEntry[] }>("/owner/catalog", { q, category, limit: 120 }),
    placeholderData: keepPreviousData,
  });

  const add = useMutation({
    mutationFn: () =>
      api.post<{ added: number; reactivated: number }>("/owner/catalog/add", {
        items: Object.entries(picked).map(([id, v]) => ({ catalog_item_id: Number(id), price: Number(v.price), quantity: Number(v.quantity) || 0 })),
      }),
    onSuccess: (r) => {
      toast.success(`${r.added + r.reactivated} products added. Customers nearby can find them now.`);
      setPicked({});
      qc.invalidateQueries({ queryKey: ["owner"] });
      router.push("/shop/inventory?sort=updated");
    },
  });

  const toggle = (c: CatalogEntry) =>
    setPicked((p) => {
      const next = { ...p };
      if (next[c.id]) delete next[c.id];
      else next[c.id] = { price: String(c.local_median ?? c.typical_price ?? ""), quantity: "5" };
      return next;
    });
  const count = Object.keys(picked).length;
  const valid = Object.values(picked).every((v) => Number(v.price) > 0);

  return (
    <div className="pb-24">
      {welcome && (
        <motion.div initial={{ opacity: 0, y: -8 }} animate={{ opacity: 1, y: 0 }} className="mb-6 flex items-start gap-3 rounded-2xl border border-brand/30 bg-brand-soft/60 p-4">
          <PartyPopper className="mt-0.5 size-5 shrink-0 text-brand" />
          <div>
            <p className="font-semibold">Your shop is live.</p>
            <p className="text-sm text-muted-foreground">Tick what you have on the shelf, check the price and count, and add them all at once. It takes a couple of minutes.</p>
          </div>
        </motion.div>
      )}
      <PageTitle title="Add from catalogue" description="Ready-made listings with specs and search words. Prices start at the local typical price; change them to yours." />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative min-w-56 flex-1">
          <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search the catalogue" className="h-9 pl-9" />
        </div>
      </div>
      <div className="-mx-4 mb-4 flex gap-2 overflow-x-auto px-4 scrollbar-none md:mx-0 md:flex-wrap md:px-0">
        <button onClick={() => setCategory(null)} className={cn("shrink-0 rounded-full border px-3 py-1.5 text-sm", !category ? "border-primary bg-primary text-primary-foreground" : "bg-card hover:bg-accent")}>
          My categories
        </button>
        {meta?.categories.map((c) => (
          <button key={c.slug} onClick={() => setCategory(c.slug)}
            className={cn("inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm", category === c.slug ? "border-primary bg-primary text-primary-foreground" : "bg-card hover:bg-accent")}>
            <AppIcon name={c.icon} className="size-3.5" /> {c.name}
          </button>
        ))}
      </div>

      {list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : !list.data ? (
        <ListSkeleton rows={6} />
      ) : (
        <ul className="divide-y rounded-2xl border bg-card">
          {list.data.items.map((c) => {
            const sel = picked[c.id];
            return (
              <li key={c.id} className={cn("flex flex-wrap items-center gap-3 p-3 sm:flex-nowrap", sel && "bg-brand-soft/40")}>
                <Checkbox checked={!!sel || c.already_listed} disabled={c.already_listed} onCheckedChange={() => toggle(c)} aria-label={`Select ${c.name}`} />
                <ProductThumb icon={c.icon} category={c.category} alt="" size="sm" />
                <button type="button" className="min-w-0 flex-1 basis-48 text-left" onClick={() => !c.already_listed && toggle(c)} disabled={c.already_listed}>
                  <p className="truncate text-sm font-medium">{c.name}</p>
                  <p className="text-xs text-muted-foreground">
                    {c.already_listed ? (
                      <span className="inline-flex items-center gap-1 text-success-ink"><Check className="size-3" /> Already in your shop</span>
                    ) : (
                      <>
                        {c.local_median ? `Typical here ${formatPrice(c.local_median)}` : c.typical_price ? `Typical ${formatPrice(c.typical_price)}` : ""}
                        {c.mrp ? ` · MRP ${formatPrice(c.mrp)}` : ""}
                      </>
                    )}
                  </p>
                </button>
                <AnimatePresence>
                  {sel && (
                    <motion.div initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} className="flex items-center gap-2">
                      <label className="flex items-center gap-1 text-xs text-muted-foreground">
                        Rs
                        <Input value={sel.price} inputMode="decimal" className="h-8 w-20 text-right tabular" aria-label="Your price"
                          onChange={(e) => setPicked((p) => ({ ...p, [c.id]: { ...p[c.id], price: e.target.value.replace(/[^\d.]/g, "") } }))} />
                      </label>
                      <label className="flex items-center gap-1 text-xs text-muted-foreground">
                        Qty
                        <Input value={sel.quantity} inputMode="numeric" className="h-8 w-14 text-right tabular" aria-label="Quantity"
                          onChange={(e) => setPicked((p) => ({ ...p, [c.id]: { ...p[c.id], quantity: e.target.value.replace(/\D/g, "") } }))} />
                      </label>
                    </motion.div>
                  )}
                </AnimatePresence>
              </li>
            );
          })}
          {!list.data.items.length && <li className="p-8 text-center text-sm text-muted-foreground">Nothing in the catalogue matches. Use &ldquo;New product&rdquo; in Inventory to add your own.</li>}
        </ul>
      )}

      <AnimatePresence>
        {count > 0 && (
          <motion.div initial={{ y: 80 }} animate={{ y: 0 }} exit={{ y: 80 }} transition={{ type: "spring", stiffness: 400, damping: 36 }}
            className="fixed inset-x-0 bottom-0 z-40 border-t bg-background/95 p-3 backdrop-blur lg:left-[248px]">
            <div className="mx-auto flex max-w-6xl items-center gap-3 px-1 md:px-3">
              <p className="text-sm"><span className="font-semibold tabular">{count}</span> selected</p>
              <Button variant="ghost" size="sm" onClick={() => setPicked({})}>Clear</Button>
              <Button className="ml-auto" disabled={!valid || add.isPending} onClick={() => add.mutate()}>
                {add.isPending && <Loader2 className="animate-spin" />} Add {count} to my shop
              </Button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
