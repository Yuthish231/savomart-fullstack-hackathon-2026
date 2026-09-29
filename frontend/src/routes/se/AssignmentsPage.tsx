import { Link } from "react-router-dom";
import { ListChecks, WifiOff } from "lucide-react";
import { useLiveQuery } from "dexie-react-hooks";
import { useMyChunks } from "@/api/studies";
import { fieldDb } from "@/offline/db";
import { Card, EmptyState, ErrorNote, PageHeader, Spinner } from "@/components/ui";

export function AssignmentsPage() {
  const { data, isLoading, error } = useMyChunks();
  const cached = useLiveQuery(() => fieldDb.chunks.toArray(), [], []);
  // Offline and the list can't load: fall back to chunks already saved on this phone.
  const list = data ?? (error ? cached?.map((c) => ({
    id: c.chunk_id, label: c.payload.chunk.label, code: c.payload.study.code, title: c.payload.study.title,
    lane_count: c.payload.chunk.lane_count, closed: 0, drafts: 0, effort_m: c.payload.chunk.effort_m, due_date: c.payload.study.due_date,
  })) : undefined);

  return (
    <div className="mx-auto max-w-2xl p-4 md:p-6">
      <PageHeader title="My assignments" subtitle="Lanes to survey, chunk by chunk. Opened chunks keep working without network." />
      {isLoading && <Spinner />}
      {error && !cached?.length && <ErrorNote error={error} />}
      {error && !!cached?.length && (
        <div className="mb-3 flex items-center gap-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
          <WifiOff className="h-4 w-4" /> No connection: showing chunks saved on this phone.
        </div>
      )}
      {list?.length === 0 && (
        <EmptyState icon={<ListChecks className="h-5 w-5" />} title="Nothing assigned yet"
          body="When your survey manager assigns a chunk of lanes it appears here." />
      )}
      <div className="space-y-3">
        {list?.map((c) => {
          const pct = c.lane_count ? Math.round((100 * c.closed) / c.lane_count) : 0;
          const offline = cached?.some((x) => x.chunk_id === c.id);
          return (
            <Link key={c.id} to={`/se/chunks/${c.id}`}>
              <Card className="p-4 transition hover:shadow-md">
                <div className="flex items-start gap-3">
                  <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-savo-purple text-lg font-bold text-savo-yellow">{c.label}</span>
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-semibold text-savo-purple">{c.code}</div>
                    <div className="truncate font-semibold text-slate-900">{c.title}</div>
                    <div className="mt-0.5 text-xs text-slate-500">
                      {c.lane_count} lanes · {(c.effort_m / 1000).toFixed(1)} km of walking
                      {c.due_date && ` · due ${new Date(c.due_date).toLocaleDateString("en-IN")}`}
                      {offline && " · saved offline"}
                    </div>
                  </div>
                </div>
                <div className="mt-3 h-2 rounded-full bg-slate-100">
                  <div className="h-2 rounded-full bg-emerald-500" style={{ width: `${pct}%` }} />
                </div>
                <div className="mt-1 text-xs text-slate-500">{c.closed}/{c.lane_count} lanes done{c.drafts ? ` · ${c.drafts} drafts` : ""}</div>
              </Card>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
