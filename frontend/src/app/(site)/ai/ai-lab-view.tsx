"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, BrainCircuit, Database, Filter, Loader2, MapPin, RefreshCw, Search, Sparkles, SplitSquareHorizontal } from "lucide-react";
import { motion } from "motion/react";
import { useState } from "react";
import { toast } from "sonner";

import { AppIcon } from "@/components/common/app-icon";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useMe } from "@/hooks/use-session";
import { api } from "@/lib/api";
import { formatNumber, timeAgo } from "@/lib/format";
import type { AiModel, SearchCompare } from "@/lib/types";
import { cn } from "@/lib/utils";

const PRESETS = ["phone charging adapter", "bathroom tap leaking", "chappal", "rainy season", "bike oil change", "school reopening"];

const PIPELINE = [
  { icon: Search, t: "Understand", d: "Normalise the query, fix spelling, add local synonyms (chappal, nali, adaptor)." },
  { icon: Sparkles, t: "Match", d: "Sentence embeddings for meaning plus SQLite FTS5 (BM25) for exact words." },
  { icon: MapPin, t: "Locate", d: "Bounding box in SQL, then exact Haversine distance to every shop." },
  { icon: Filter, t: "Filter", d: "Stock, price range, pickup or delivery eligibility." },
  { icon: SplitSquareHorizontal, t: "Rank and group", d: "75% relevance, 15% proximity, 10% availability. Same item across shops is grouped." },
];

function metricLines(m: AiModel): [string, string][] {
  const x = m.metrics as Record<string, number | null | Record<string, number>>;
  switch (m.name) {
    case "embeddings":
      return [["Listings indexed", formatNumber(Number(x.listings_indexed ?? 0))], ["Vector size", String(x.dimensions ?? "-")]];
    case "word2vec":
      return [["Training sentences", formatNumber(Number(x.sentences ?? 0))], ["Vocabulary", formatNumber(Number(x.vocabulary ?? 0))]];
    case "demand":
      return [
        ["Error per week (MAE)", x.mae_7d !== undefined ? `${x.mae_7d} units` : "-"],
        ["Naive baseline MAE", x.naive_mae_7d !== undefined ? `${x.naive_mae_7d} units` : "-"],
        ["Better than baseline", x.improvement_pct !== undefined ? `${x.improvement_pct}%` : "-"],
        ["R squared", String(x.r2 ?? "-")],
      ];
    case "recommendations":
      return [
        ["Baskets analysed", formatNumber(Number(x.baskets ?? 0))],
        ["Rules found", String(x.rules ?? 0)],
        ["Avg confidence", x.avg_confidence ? `${Math.round(Number(x.avg_confidence) * 100)}%` : "-"],
        ["Avg lift", String(x.avg_lift ?? "-")],
      ];
    case "anomalies":
      return [
        ["Listings compared", formatNumber(Number(x.listings_checked ?? 0))],
        ["Item groups", String(x.item_groups ?? 0)],
        ["Isolated by forest", String(x.isolated_by_forest ?? 0)],
        ["Flagged for review", String(x.flagged_for_review ?? 0)],
      ];
    default:
      return [];
  }
}

export function AiLabView() {
  const qc = useQueryClient();
  const { data: me } = useMe();
  const [input, setInput] = useState("phone charging adapter");
  const [query, setQuery] = useState("phone charging adapter");

  const models = useQuery({
    queryKey: ["ai", "models"],
    queryFn: () => api.get<{ training: boolean; models: AiModel[] }>("/ai/models"),
    refetchInterval: (q) => (q.state.data?.training ? 3000 : false),
  });
  const compare = useQuery({
    queryKey: ["ai", "compare", query],
    queryFn: () => api.get<SearchCompare>("/ai/search-compare", { q: query }),
    enabled: query.length >= 2,
  });
  const retrain = useMutation({
    mutationFn: () => api.post<{ started: boolean; message?: string }>("/ai/retrain"),
    onSuccess: (r) => {
      toast[r.started ? "success" : "info"](r.started ? "Retraining all models. This takes about 20 seconds." : r.message ?? "Already running");
      qc.invalidateQueries({ queryKey: ["ai", "models"] });
    },
  });

  const demandFeatures = (models.data?.models.find((m) => m.name === "demand")?.metrics.feature_importance ?? {}) as Record<string, number>;

  return (
    <div className="mx-auto max-w-7xl px-4 pt-10 md:px-6 md:pt-14">
      <div className="max-w-3xl">
        <Badge variant="outline" className="gap-1.5"><BrainCircuit className="size-3.5 text-brand" /> AI Lab</Badge>
        <h1 className="mt-4 text-4xl font-semibold md:text-5xl">The machine learning behind NearShop</h1>
        <p className="mt-4 text-lg text-muted-foreground">
          Five models, all trained on this deployment&apos;s own data, all with their numbers on show. Where a model learned from seeded demo data, it says so.
        </p>
      </div>

      {/* ------------------------------------------------------------ search comparison */}
      <section className="mt-12">
        <h2 className="text-2xl font-semibold">Search: four methods, one query</h2>
        <p className="mt-1 text-muted-foreground">Keyword search only finds exact words. Watch what meaning-based search adds.</p>
        <form className="mt-5 flex max-w-xl gap-2" onSubmit={(e) => { e.preventDefault(); setQuery(input.trim()); }}>
          <Input value={input} onChange={(e) => setInput(e.target.value)} className="h-11" aria-label="Query to compare" />
          <Button type="submit" size="lg" className="h-11">Compare</Button>
        </form>
        <div className="mt-3 flex flex-wrap gap-2">
          {PRESETS.map((p) => (
            <button key={p} onClick={() => { setInput(p); setQuery(p); }}
              className={cn("rounded-full border px-3 py-1 text-sm transition-colors", query === p ? "border-primary bg-primary text-primary-foreground" : "bg-card hover:bg-accent")}>{p}</button>
          ))}
        </div>
        <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          {(compare.data?.methods ?? Array.from({ length: 4 }).map(() => null)).map((m, i) =>
            m ? (
              <motion.div key={m.key} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}
                className={cn("rounded-2xl border bg-card p-4", m.key === "hybrid" && "border-brand/40 ring-4 ring-brand/5")}>
                <p className="font-semibold">{m.title}</p>
                <p className="line-clamp-2 min-h-8 text-xs text-muted-foreground">{m.note}</p>
                <ol className="mt-3 space-y-2">
                  {m.results.map((r, j) => (
                    <li key={`${r.name}-${j}`} className="flex items-center gap-2 text-sm">
                      <span className="grid size-6 shrink-0 place-items-center rounded-md bg-muted"><AppIcon name={r.icon} className="size-3.5" /></span>
                      <span className="min-w-0 flex-1 truncate">{r.name}</span>
                      <span className="text-xs text-muted-foreground tabular">{r.score.toFixed(2)}</span>
                    </li>
                  ))}
                  {!m.results.length && <li className="py-4 text-center text-sm text-muted-foreground">No results</li>}
                </ol>
              </motion.div>
            ) : (
              <Skeleton key={i} className="h-72 rounded-2xl" />
            ),
          )}
        </div>
        <ol className="mt-8 grid gap-3 md:grid-cols-5">
          {PIPELINE.map((s, i) => (
            <li key={s.t} className="relative rounded-2xl border bg-card p-4">
              <s.icon className="size-5 text-brand" />
              <p className="mt-3 text-sm font-semibold">{i + 1}. {s.t}</p>
              <p className="mt-1 text-xs text-muted-foreground">{s.d}</p>
              {i < PIPELINE.length - 1 && <ArrowRight className="absolute top-1/2 -right-2.5 hidden size-4 -translate-y-1/2 text-muted-foreground md:block" />}
            </li>
          ))}
        </ol>
      </section>

      {/* ------------------------------------------------------------ model cards */}
      <section className="mt-16">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold">Model cards</h2>
            <p className="mt-1 text-muted-foreground">Live from the last training run.</p>
          </div>
          {me?.role === "admin" && (
            <Button onClick={() => retrain.mutate()} disabled={retrain.isPending || models.data?.training}>
              {models.data?.training ? <Loader2 className="animate-spin" /> : <RefreshCw />} {models.data?.training ? "Training..." : "Retrain all models"}
            </Button>
          )}
        </div>
        <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {(models.data?.models ?? Array.from({ length: 5 }).map(() => null)).map((m, i) =>
            m ? (
              <article key={m.name} className="flex flex-col rounded-2xl border bg-card p-5">
                <div className="flex items-start justify-between gap-3">
                  <h3 className="font-semibold">{m.title}</h3>
                  {m.uses_demo_data && <Badge variant="outline" className="shrink-0 text-[10px]">Demo data</Badge>}
                </div>
                <p className="mt-1 text-sm text-muted-foreground">{m.purpose}</p>
                <p className="mt-3 font-mono text-xs text-brand-ink">{m.algorithm ?? "not trained"}</p>
                <dl className="mt-4 grid grid-cols-2 gap-2">
                  {metricLines(m).map(([k, v]) => (
                    <div key={k} className="rounded-xl bg-muted/60 p-2.5">
                      <dt className="text-[11px] text-muted-foreground">{k}</dt>
                      <dd className="text-sm font-semibold tabular">{v}</dd>
                    </div>
                  ))}
                </dl>
                {m.name === "demand" && Object.keys(demandFeatures).length > 0 && (
                  <div className="mt-4">
                    <p className="text-xs font-medium text-muted-foreground">What drives the forecast</p>
                    <ul className="mt-2 space-y-1">
                      {Object.entries(demandFeatures).slice(0, 5).map(([f, v]) => (
                        <li key={f} className="flex items-center gap-2 text-xs">
                          <span className="w-24 shrink-0 font-mono">{f}</span>
                          <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted"><span className="block h-full rounded-full bg-brand" style={{ width: `${v * 100}%` }} /></span>
                          <span className="w-9 text-right tabular text-muted-foreground">{Math.round(v * 100)}%</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                <p className="mt-auto flex items-center gap-1.5 pt-4 text-xs text-muted-foreground">
                  <Database className="size-3.5" /> {m.note}
                </p>
                <p className="mt-1 text-xs text-muted-foreground" suppressHydrationWarning>
                  {m.trained_at ? `Trained ${timeAgo(m.trained_at)} in ${(m.duration_ms / 1000).toFixed(1)} s` : "Not trained yet"}
                </p>
              </article>
            ) : (
              <Skeleton key={i} className="h-72 rounded-2xl" />
            ),
          )}
        </div>
      </section>
    </div>
  );
}
