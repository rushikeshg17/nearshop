"use client";

import { ChevronDown, Crosshair, Loader2, MapPin } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Slider } from "@/components/ui/slider";
import { useMeta } from "@/hooks/use-session";
import { useLocation } from "@/lib/location";
import { cn } from "@/lib/utils";

export function LocationPicker({ className, align = "start" }: { className?: string; align?: "start" | "end" | "center" }) {
  const { location, radiusKm, setLocation, setRadiusKm, requestGps } = useLocation();
  const { data: meta } = useMeta();
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const [locating, setLocating] = useState(false);

  const localities = (meta?.city.localities ?? []).filter((l) => l.name.toLowerCase().includes(filter.toLowerCase()));

  async function useGps() {
    setLocating(true);
    const res = await requestGps();
    setLocating(false);
    if (res.ok) {
      toast.success("Showing shops near your current location");
      setOpen(false);
    } else toast.error(res.message ?? "Couldn't get your location");
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          className={cn(
            "group inline-flex min-w-0 items-center gap-1.5 rounded-full border bg-card px-3 py-1.5 text-sm shadow-soft transition-colors hover:bg-accent focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none",
            className,
          )}
          aria-label="Change location"
        >
          <MapPin className="size-4 shrink-0 text-brand" />
          <span className="truncate font-medium">{location?.label ?? "Set location"}</span>
          <span className="shrink-0 text-muted-foreground tabular">· {radiusKm} km</span>
          <ChevronDown className="size-3.5 shrink-0 text-muted-foreground transition-transform group-data-[state=open]:rotate-180" />
        </button>
      </PopoverTrigger>
      <PopoverContent align={align} className="w-80 p-0">
        <div className="space-y-3 border-b p-4">
          <p className="text-sm font-semibold">Where are you shopping?</p>
          <Button variant="outline" className="w-full justify-start" onClick={useGps} disabled={locating}>
            {locating ? <Loader2 className="animate-spin" /> : <Crosshair />}
            Use my current location
          </Button>
          <div>
            <div className="mb-2 flex items-center justify-between text-sm">
              <span className="text-muted-foreground">Search radius</span>
              <span className="font-medium tabular">{radiusKm} km</span>
            </div>
            <Slider
              min={1}
              max={15}
              step={1}
              value={[radiusKm]}
              onValueChange={([v]) => setRadiusKm(v)}
              aria-label="Search radius in kilometres"
            />
          </div>
        </div>
        <div className="p-2">
          <Input
            placeholder={`Search areas in ${meta?.city.name ?? "your city"}`}
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="mb-1 h-9"
          />
          <ScrollArea className="h-56">
            <ul className="py-1">
              {localities.map((l) => {
                const active = location?.source === "locality" && location.label === l.name;
                return (
                  <li key={l.name}>
                    <button
                      onClick={() => {
                        setLocation({ lat: l.lat, lng: l.lng, label: l.name, source: "locality" });
                        setOpen(false);
                      }}
                      className={cn(
                        "flex w-full items-center justify-between rounded-md px-2.5 py-2 text-left text-sm hover:bg-accent",
                        active && "bg-brand-soft text-brand-ink",
                      )}
                    >
                      <span>{l.name}</span>
                      {l.pincode && <span className="text-xs text-muted-foreground tabular">{l.pincode}</span>}
                    </button>
                  </li>
                );
              })}
              {!localities.length && <li className="px-2.5 py-6 text-center text-sm text-muted-foreground">No matching area</li>}
            </ul>
          </ScrollArea>
        </div>
      </PopoverContent>
    </Popover>
  );
}
