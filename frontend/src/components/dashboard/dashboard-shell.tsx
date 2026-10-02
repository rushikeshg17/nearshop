"use client";

import { ExternalLink, Menu } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { Logo } from "@/components/brand/logo";
import { NotificationsBell } from "@/components/site/notifications-bell";
import { UserMenu } from "@/components/site/user-menu";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { useMe } from "@/hooks/use-session";
import { cn } from "@/lib/utils";

export interface NavItem {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: number;
  exact?: boolean;
}

function NavList({ items, onNavigate }: { items: NavItem[]; onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <ul className="space-y-0.5">
      {items.map((item) => {
        const active = item.exact ? pathname === item.href : pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <li key={item.href}>
            <Link
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cn(
                "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                active ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
              )}
            >
              <item.icon className={cn("size-4", active && "text-brand")} />
              <span className="flex-1">{item.label}</span>
              {!!item.badge && (
                <span className="grid min-w-5 place-items-center rounded-full bg-brand px-1.5 text-[11px] leading-5 font-semibold text-brand-foreground tabular">
                  {item.badge}
                </span>
              )}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

export function DashboardShell({
  title,
  subtitle,
  items,
  publicHref,
  children,
}: {
  title: string;
  subtitle?: string;
  items: NavItem[];
  publicHref?: string;
  children: React.ReactNode;
}) {
  const { data: me } = useMe();
  const [open, setOpen] = useState(false);
  return (
    <div className="min-h-dvh bg-surface/60 lg:grid lg:grid-cols-[248px_1fr]">
      <aside className="sticky top-0 hidden h-dvh flex-col border-r bg-background px-3 py-4 lg:flex">
        <Logo className="px-2" />
        <div className="mt-6 px-3">
          <p className="truncate text-sm font-semibold">{title}</p>
          {subtitle && <p className="truncate text-xs text-muted-foreground">{subtitle}</p>}
        </div>
        <nav className="mt-4 flex-1" aria-label="Dashboard">
          <NavList items={items} />
        </nav>
        {publicHref && (
          <Link href={publicHref} className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-muted-foreground hover:bg-accent/60 hover:text-foreground">
            <ExternalLink className="size-4" /> View public page
          </Link>
        )}
      </aside>
      <div className="min-w-0">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b bg-background/85 px-4 backdrop-blur-xl md:px-6">
          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open menu"><Menu /></Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-72 p-4">
              <SheetTitle className="sr-only">Menu</SheetTitle>
              <Logo />
              <p className="mt-6 px-3 text-sm font-semibold">{title}</p>
              <nav className="mt-3"><NavList items={items} onNavigate={() => setOpen(false)} /></nav>
            </SheetContent>
          </Sheet>
          <p className="truncate text-sm font-semibold lg:hidden">{title}</p>
          <div className="ml-auto flex items-center gap-1">
            <Button asChild variant="ghost" size="sm" className="hidden sm:inline-flex"><Link href="/">Customer view</Link></Button>
            {me && <NotificationsBell />}
            {me && <UserMenu user={me} />}
          </div>
        </header>
        <main id="main" className="mx-auto max-w-6xl px-4 py-6 md:px-6 md:py-8">{children}</main>
      </div>
    </div>
  );
}

export function PageTitle({ title, description, action }: { title: string; description?: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold md:text-3xl">{title}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {action}
    </div>
  );
}

export function StatTile({
  label,
  value,
  hint,
  icon: Icon,
  tone = "default",
  href,
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  icon?: React.ComponentType<{ className?: string }>;
  tone?: "default" | "brand" | "warning" | "success";
  href?: string;
}) {
  const body = (
    <>
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm text-muted-foreground">{label}</p>
        {Icon && (
          <Icon
            className={cn(
              "size-4",
              tone === "brand" ? "text-brand" : tone === "warning" ? "text-warning" : tone === "success" ? "text-success" : "text-muted-foreground",
            )}
          />
        )}
      </div>
      <p className="mt-2 font-heading text-2xl font-semibold tracking-tight tabular">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
    </>
  );
  const cls = "block rounded-2xl border bg-card p-4 transition-shadow";
  return href ? <Link href={href} className={cn(cls, "hover:shadow-lift")}>{body}</Link> : <div className={cls}>{body}</div>;
}
