"use client";

import { Store } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense, useEffect } from "react";

import { Logo } from "@/components/brand/logo";
import { registerCategoryHues } from "@/components/common/product-thumb";
import { LocationPicker } from "@/components/site/location-picker";
import { NotificationsBell } from "@/components/site/notifications-bell";
import { SearchBox } from "@/components/site/search-box";
import { ThemeToggle, UserMenu } from "@/components/site/user-menu";
import { Button } from "@/components/ui/button";
import { useMe, useMeta } from "@/hooks/use-session";
import { cn } from "@/lib/utils";

export function SiteHeader() {
  const pathname = usePathname();
  const { data: me, isLoading } = useMe();
  const { data: meta } = useMeta();
  const isHome = pathname === "/";

  useEffect(() => {
    if (meta) registerCategoryHues(meta.categories);
  }, [meta]);

  return (
    <header className="sticky top-0 z-40 border-b border-transparent bg-background/80 backdrop-blur-xl supports-[backdrop-filter]:bg-background/70 [&:not(:hover)]:border-border/60">
      <div className="mx-auto flex h-16 max-w-7xl items-center gap-3 px-4 md:gap-5 md:px-6">
        <Logo className="shrink-0" />
        <div className={cn("hidden min-w-0 flex-1 items-center gap-3 md:flex", isHome && "md:invisible")}>
          <Suspense>
            <SearchBox className="max-w-xl" />
          </Suspense>
          <LocationPicker className="max-w-56 shrink-0" />
        </div>
        <div className="flex-1 md:hidden" />
        <nav className="flex shrink-0 items-center gap-1">
          <Link
            href="/shops"
            className={cn(
              "hidden rounded-full px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground xl:inline-flex",
              pathname.startsWith("/shops") && "text-foreground",
            )}
          >
            Shops
          </Link>
          <Link
            href="/ai"
            className={cn(
              "hidden rounded-full px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground xl:inline-flex",
              pathname === "/ai" && "text-foreground",
            )}
          >
            AI Lab
          </Link>
          {me && <NotificationsBell />}
          {isLoading ? (
            <div className="size-9" />
          ) : me ? (
            <UserMenu user={me} />
          ) : (
            <>
              <ThemeToggle />
              <Button asChild variant="ghost" className="hidden h-9 rounded-full px-4 sm:inline-flex">
                <Link href="/register/shop">
                  <Store /> List your shop
                </Link>
              </Button>
              <Button asChild className="h-9 rounded-full px-4">
                <Link href={`/login?next=${encodeURIComponent(pathname)}`}>Sign in</Link>
              </Button>
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
