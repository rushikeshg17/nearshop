"use client";

import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts";

import { type ChartConfig, ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { formatCompactPrice } from "@/lib/format";
import type { SalesPoint } from "@/lib/types";

const config = {
  revenue: { label: "Revenue", color: "var(--chart-1)" },
  units: { label: "Units", color: "var(--chart-2)" },
} satisfies ChartConfig;

export function SalesChart({ data, className }: { data: SalesPoint[]; className?: string }) {
  const rows = data.map((d) => ({
    ...d,
    label: new Date(`${d.date}T00:00:00`).toLocaleDateString("en-IN", { day: "numeric", month: "short" }),
  }));
  return (
    <ChartContainer config={config} className={className ?? "h-56 w-full"}>
      <AreaChart data={rows} margin={{ left: 4, right: 8, top: 8, bottom: 0 }} accessibilityLayer>
        <defs>
          <linearGradient id="fillRevenue" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor="var(--color-revenue)" stopOpacity={0.28} />
            <stop offset="95%" stopColor="var(--color-revenue)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid vertical={false} strokeDasharray="3 3" />
        <XAxis dataKey="label" tickLine={false} axisLine={false} minTickGap={28} tickMargin={8} />
        <YAxis tickLine={false} axisLine={false} width={52} tickFormatter={(v: number) => formatCompactPrice(v)} />
        <ChartTooltip
          cursor={{ strokeDasharray: "3 3" }}
          content={<ChartTooltipContent formatter={(value, name) => (name === "revenue" ? formatCompactPrice(Number(value)) : `${value} units`)} />}
        />
        <Area dataKey="revenue" type="monotone" stroke="var(--color-revenue)" strokeWidth={2} fill="url(#fillRevenue)" />
      </AreaChart>
    </ChartContainer>
  );
}
