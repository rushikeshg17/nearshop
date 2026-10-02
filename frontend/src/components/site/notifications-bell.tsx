"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useNow } from "@/hooks/use-debounce";
import { api } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import type { Notification } from "@/lib/types";
import { cn } from "@/lib/utils";

export function NotificationsBell() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const now = useNow(60_000);

  // Polling keeps the badge honest without websockets. Also refreshes queues when something changes.
  const unread = useQuery({
    queryKey: ["notifications", "unread"],
    queryFn: () => api.get<{ unread: number }>("/notifications/unread-count"),
    refetchInterval: 15_000,
    refetchIntervalInBackground: false,
  });
  const list = useQuery({
    queryKey: ["notifications", "list"],
    queryFn: () => api.get<{ items: Notification[]; unread: number }>("/notifications", { limit: 30 }),
    enabled: open,
  });
  const markRead = useMutation({
    mutationFn: (ids?: number[]) => api.post("/notifications/read", { ids: ids ?? null }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const count = unread.data?.unread ?? 0;

  return (
    <Popover
      open={open}
      onOpenChange={(o) => {
        setOpen(o);
        if (o) {
          // new notifications usually mean a status changed somewhere
          qc.invalidateQueries({ queryKey: ["reservations"] });
          qc.invalidateQueries({ queryKey: ["orders"] });
        }
      }}
    >
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon-lg" className="relative rounded-full" aria-label={`Notifications${count ? `, ${count} unread` : ""}`}>
          <Bell className="size-[18px]" />
          {count > 0 && (
            <span className="absolute top-1 right-1 grid min-w-4 place-items-center rounded-full bg-brand px-1 text-[10px] leading-4 font-semibold text-brand-foreground tabular">
              {count > 9 ? "9+" : count}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[min(92vw,380px)] p-0">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <p className="text-sm font-semibold">Notifications</p>
          {count > 0 && (
            <Button variant="ghost" size="xs" onClick={() => markRead.mutate(undefined)}>
              <CheckCheck /> Mark all read
            </Button>
          )}
        </div>
        <ScrollArea className="max-h-[420px]">
          {list.isLoading ? (
            <p className="p-6 text-center text-sm text-muted-foreground">Loading...</p>
          ) : !list.data?.items.length ? (
            <p className="p-8 text-center text-sm text-muted-foreground">You&apos;re all caught up.</p>
          ) : (
            <ul className="divide-y">
              {list.data.items.map((n) => (
                <li key={n.id}>
                  <Link
                    href={n.link ?? "#"}
                    onClick={() => {
                      if (!n.read) markRead.mutate([n.id]);
                      setOpen(false);
                    }}
                    className={cn("flex gap-3 px-4 py-3 transition-colors hover:bg-accent", !n.read && "bg-brand-soft/40")}
                  >
                    <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", n.read ? "bg-transparent" : "bg-brand")} />
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-medium">{n.title}</span>
                      {n.body && <span className="mt-0.5 block text-sm text-muted-foreground">{n.body}</span>}
                      <span className="mt-1 block text-xs text-muted-foreground" suppressHydrationWarning>
                        {timeAgo(n.created_at, now)}
                      </span>
                    </span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </ScrollArea>
      </PopoverContent>
    </Popover>
  );
}
