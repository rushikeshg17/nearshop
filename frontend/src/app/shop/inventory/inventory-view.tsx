"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, FileSpreadsheet, Library, Minus, MoreHorizontal, Package, Pencil, Plus, Search, Trash2, Undo2 } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";

import { Freshness, StockPill } from "@/components/common/indicators";
import { ProductThumb } from "@/components/common/product-thumb";
import { EmptyState, ErrorState, ListSkeleton } from "@/components/common/states";
import { PageTitle } from "@/components/dashboard/dashboard-shell";
import { ConfirmAction } from "@/components/fulfillment/confirm-action";
import { ProductFormDialog } from "@/components/owner/product-form-dialog";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useDebounce } from "@/hooks/use-debounce";
import { useMeta } from "@/hooks/use-session";
import { api } from "@/lib/api";
import { formatPrice } from "@/lib/format";
import type { Listing, OwnerListing } from "@/lib/types";
import { cn } from "@/lib/utils";

type Page = { items: OwnerListing[]; total: number; page: number; page_size: number };
const STOCK_TABS = [
  { value: "all", label: "All" },
  { value: "low_stock", label: "Low" },
  { value: "out_of_stock", label: "Out" },
  { value: "inactive", label: "Removed" },
];

export function InventoryView() {
  const router = useRouter();
  const params = useSearchParams();
  const { data: meta } = useMeta();
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<OwnerListing | null>(null);
  const stock = params.get("stock") ?? "all";
  const category = params.get("category") ?? "";
  const sort = params.get("sort") ?? "name";
  const focus = Number(params.get("focus")) || null;
  const q = useDebounce(search, 250);

  const setParam = (k: string, v: string | null) => {
    const next = new URLSearchParams(params.toString());
    if (!v || v === "all") next.delete(k);
    else next.set(k, v);
    next.delete("focus");
    router.replace(`/shop/inventory?${next.toString()}`, { scroll: false });
  };

  const list = useQuery({
    queryKey: ["owner", "products", q, stock, category, sort],
    queryFn: () => api.get<Page>("/owner/products", { q, stock, category, sort, page_size: 200 }),
    placeholderData: keepPreviousData,
  });

  return (
    <>
      <PageTitle
        title="Inventory"
        description="Keep counts honest. Customers see how recently you updated, and fresh shops rank higher."
        action={
          <div className="flex gap-2">
            <Button asChild variant="outline"><Link href="/shop/import"><FileSpreadsheet /> Import Excel</Link></Button>
            <Button asChild variant="outline"><Link href="/shop/catalog"><Library /> Add from catalogue</Link></Button>
            <Button onClick={() => setCreating(true)}><Plus /> New product</Button>
          </div>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative min-w-56 flex-1">
          <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search your products or SKU" className="h-9 pl-9" />
        </div>
        <Tabs value={stock} onValueChange={(v) => setParam("stock", v)}>
          <TabsList>{STOCK_TABS.map((t) => <TabsTrigger key={t.value} value={t.value}>{t.label}</TabsTrigger>)}</TabsList>
        </Tabs>
        <Select value={category || "all"} onValueChange={(v) => setParam("category", v)}>
          <SelectTrigger className="h-9 w-40"><SelectValue placeholder="Category" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All categories</SelectItem>
            {meta?.categories.map((c) => <SelectItem key={c.slug} value={c.slug}>{c.name}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={sort} onValueChange={(v) => setParam("sort", v === "name" ? null : v)}>
          <SelectTrigger className="h-9 w-40"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="name">Name</SelectItem>
            <SelectItem value="stock_asc">Lowest stock</SelectItem>
            <SelectItem value="stock_desc">Highest stock</SelectItem>
            <SelectItem value="price_asc">Price: low to high</SelectItem>
            <SelectItem value="updated">Recently updated</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {list.isError ? (
        <ErrorState error={list.error} onRetry={() => list.refetch()} />
      ) : !list.data ? (
        <ListSkeleton rows={6} />
      ) : list.data.items.length === 0 ? (
        <EmptyState icon={Package} title={q || stock !== "all" ? "No products match" : "No products yet"}
          description={q || stock !== "all" ? "Try another search or filter." : "Add products from the ready catalogue in a couple of minutes."}
          action={<Button asChild><Link href="/shop/catalog">Open catalogue</Link></Button>} />
      ) : (
        <>
          <p className="mb-2 text-xs text-muted-foreground">{list.data.total} listings</p>
          <ul className={cn("divide-y rounded-2xl border bg-card transition-opacity", list.isFetching && "opacity-70")}>
            {list.data.items.map((p) => (
              <InventoryRow key={p.id} p={p} focused={p.id === focus} onEdit={() => setEditing(p)} />
            ))}
          </ul>
        </>
      )}
      {creating && <ProductFormDialog open onOpenChange={setCreating} />}
      {editing && <ProductFormDialog key={editing.id} product={editing} open onOpenChange={(o) => !o && setEditing(null)} />}
    </>
  );
}

function InventoryRow({ p, focused, onEdit }: { p: OwnerListing; focused: boolean; onEdit: () => void }) {
  const qc = useQueryClient();
  const ref = useRef<HTMLLIElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [qty, setQty] = useState(p.quantity);
  const [confirmRemove, setConfirmRemove] = useState(false);
  const [price, setPrice] = useState(String(p.price));
  const dirtyQty = qty !== p.quantity;
  const dirtyPrice = Number(price) !== p.price && Number(price) > 0;

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- keep local edits in sync after a refetch
    setQty(p.quantity);
    setPrice(String(p.price));
  }, [p.quantity, p.price]);
  useEffect(() => {
    if (focused) ref.current?.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [focused]);

  const invalidate = () => qc.invalidateQueries({ queryKey: ["owner"] });
  const saveStock = useMutation({
    mutationFn: () => api.put<Listing>(`/owner/products/${p.id}/stock`, { quantity: qty }),
    onSuccess: () => {
      toast.success(`${p.name}: stock set to ${qty}`);
      invalidate();
    },
  });
  const savePrice = useMutation({
    mutationFn: () => api.patch(`/owner/products/${p.id}`, { price: Number(price) }),
    onSuccess: () => {
      toast.success(`Price updated to ${formatPrice(Number(price))}`);
      invalidate();
    },
  });
  const remove = useMutation({
    mutationFn: () => api.delete(`/owner/products/${p.id}`),
    onSuccess: () => {
      toast.success("Removed from your shop. Past orders keep their history.");
      invalidate();
    },
  });
  const restore = useMutation({
    mutationFn: () => api.patch(`/owner/products/${p.id}`, { is_active: true }),
    onSuccess: () => {
      toast.success("Listed again");
      invalidate();
    },
  });
  const upload = useMutation({
    mutationFn: (file: File) => api.upload(`/owner/products/${p.id}/image`, file),
    onSuccess: () => {
      toast.success("Photo updated");
      invalidate();
    },
  });

  return (
    <li ref={ref} className={cn("flex flex-wrap items-center gap-x-4 gap-y-3 p-3 sm:flex-nowrap", focused && "bg-brand-soft/50", !p.is_active && "opacity-60")}>
      <button type="button" onClick={() => fileRef.current?.click()} className="group relative shrink-0 rounded-lg" aria-label={`Upload photo for ${p.name}`}>
        <ProductThumb icon={p.icon} imageUrl={p.image_url} category={p.category} alt="" size="sm" />
        <span className="absolute inset-0 grid place-items-center rounded-lg bg-black/40 text-white opacity-0 transition-opacity group-hover:opacity-100"><Camera className="size-4" /></span>
      </button>
      <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={(e) => e.target.files?.[0] && upload.mutate(e.target.files[0])} />

      <div className="min-w-0 flex-1 basis-48">
        <p className="truncate text-sm font-medium">{p.name}</p>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-1">
          <StockPill status={p.stock_status} quantity={p.quantity} compact />
          <Freshness at={p.stock_updated_at} />
          {p.sku && <span className="font-mono text-[11px] text-muted-foreground">{p.sku}</span>}
        </div>
      </div>

      {p.is_active && (
        <>
          <form
            className="flex items-center gap-1"
            onSubmit={(e) => {
              e.preventDefault();
              if (dirtyPrice) savePrice.mutate();
            }}
          >
            <span className="text-sm text-muted-foreground">Rs</span>
            <Input value={price} onChange={(e) => setPrice(e.target.value.replace(/[^\d.]/g, ""))} onBlur={() => dirtyPrice && savePrice.mutate()}
              inputMode="decimal" className="h-8 w-20 text-right tabular" aria-label={`Price of ${p.name}`} />
          </form>

          <form
            className="flex items-center gap-1"
            onSubmit={(e) => {
              e.preventDefault();
              saveStock.mutate();
            }}
          >
            <div className="flex items-center rounded-lg border">
              <Button type="button" variant="ghost" size="icon-sm" onClick={() => setQty(Math.max(0, qty - 1))} aria-label="Decrease stock"><Minus /></Button>
              <Input value={qty} onChange={(e) => setQty(Math.max(0, Number(e.target.value.replace(/\D/g, "")) || 0))} inputMode="numeric"
                className="h-7 w-12 border-0 px-0 text-center tabular shadow-none focus-visible:ring-0" aria-label={`Stock of ${p.name}`} />
              <Button type="button" variant="ghost" size="icon-sm" onClick={() => setQty(qty + 1)} aria-label="Increase stock"><Plus /></Button>
            </div>
            <Button type="submit" size="sm" variant={dirtyQty ? "default" : "outline"} disabled={saveStock.isPending} className="w-20">
              {dirtyQty ? "Save" : "Recount"}
            </Button>
          </form>
        </>
      )}

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon-sm" aria-label={`More actions for ${p.name}`}><MoreHorizontal /></Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={onEdit}><Pencil /> Edit details</DropdownMenuItem>
          <DropdownMenuItem onClick={() => fileRef.current?.click()}><Camera /> Upload photo</DropdownMenuItem>
          <DropdownMenuItem asChild><Link href={`/product/${p.id}`}>View as customer</Link></DropdownMenuItem>
          <DropdownMenuSeparator />
          {p.is_active ? (
            <DropdownMenuItem variant="destructive" onClick={() => setConfirmRemove(true)}><Trash2 /> Remove from shop</DropdownMenuItem>
          ) : (
            <DropdownMenuItem onClick={() => restore.mutate()}><Undo2 /> List again</DropdownMenuItem>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
      <ConfirmAction open={confirmRemove} onOpenChange={setConfirmRemove} title={`Remove ${p.name}?`}
        description="It disappears from search. Past orders and reviews keep their history." confirmLabel="Remove"
        onConfirm={() => remove.mutate()} pending={remove.isPending} />
    </li>
  );
}
