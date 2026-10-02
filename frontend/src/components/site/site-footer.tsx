import Link from "next/link";

import { Logo } from "@/components/brand/logo";

export function SiteFooter() {
  return (
    <footer className="mt-24 border-t bg-surface/50 pb-24 md:pb-0">
      <div className="mx-auto grid max-w-7xl gap-10 px-4 py-12 md:grid-cols-[1.4fr_1fr_1fr_1fr] md:px-6">
        <div className="space-y-3">
          <Logo />
          <p className="max-w-xs text-sm text-muted-foreground">
            Local inventory, online. See what the shops around you have in stock, then reserve it or get it delivered by the shop.
          </p>
        </div>
        <div>
          <p className="mb-3 text-sm font-semibold">Shop</p>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li><Link href="/search" className="hover:text-foreground">Search nearby</Link></li>
            <li><Link href="/shops" className="hover:text-foreground">Browse shops</Link></li>
            <li><Link href="/account" className="hover:text-foreground">Your reservations</Link></li>
          </ul>
        </div>
        <div>
          <p className="mb-3 text-sm font-semibold">For shops</p>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li><Link href="/register/shop" className="hover:text-foreground">List your shop</Link></li>
            <li><Link href="/shop" className="hover:text-foreground">Shop dashboard</Link></li>
          </ul>
        </div>
        <div>
          <p className="mb-3 text-sm font-semibold">How it works</p>
          <ul className="space-y-2 text-sm text-muted-foreground">
            <li><Link href="/ai" className="hover:text-foreground">AI Lab</Link></li>
            <li><Link href="/#how" className="hover:text-foreground">Pickup and delivery</Link></li>
          </ul>
        </div>
      </div>
      <div className="border-t">
        <p className="mx-auto max-w-7xl px-4 py-5 text-xs text-muted-foreground md:px-6">
          Map data from OpenStreetMap contributors. Demo data: shops, prices and sales are generated for demonstration.
        </p>
      </div>
    </footer>
  );
}
