import { Link } from "react-router-dom";
import { Building2, PlusCircle } from "lucide-react";
import { useProperties } from "@/api/properties";
import { Button, Card, EmptyState, ErrorNote, PageHeader, Spinner } from "@/components/ui";
import { FlagChips, RecPill, StageBadge, ago } from "@/components/property";
import { useDrafts } from "@/stores/draft";

export function MyPropertiesPage() {
  const { data, isLoading, error } = useProperties();
  const draft = useDrafts((s) => s.drafts.new);

  return (
    <div className="mx-auto max-w-3xl p-4 md:p-6">
      <PageHeader title="My properties" subtitle="What you've onboarded, how it scored and where it stands"
        actions={<Link to="/bde/new"><Button><PlusCircle className="h-4 w-4" /> Add</Button></Link>} />
      {draft?.name && (
        <Link to="/bde/new">
          <Card className="mb-3 border-dashed border-savo-purple/50 bg-savo-purple-light/40 p-3 text-sm">
            <span className="font-semibold text-savo-purple">Unsent draft:</span> {draft.name} · continue where you left off
          </Card>
        </Link>
      )}
      {isLoading && <Spinner />}
      {error && <ErrorNote error={error} />}
      {data?.length === 0 && !draft?.name && (
        <EmptyState icon={<Building2 className="h-5 w-5" />} title="Nothing onboarded yet"
          body="Spotted a vacant shop? Add it: it takes about two minutes and is evaluated automatically." />
      )}
      <div className="space-y-2">
        {data?.map((p) => (
          <Link key={p.id} to={`/bde/properties/${p.id}`}>
            <Card className="flex items-center gap-3 p-3 transition hover:shadow-md">
              {p.cover_photo ? (
                <img src={p.cover_photo} alt="" className="h-14 w-14 shrink-0 rounded-lg object-cover" />
              ) : (
                <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-lg bg-slate-100"><Building2 className="h-5 w-5 text-slate-400" /></div>
              )}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[11px] font-semibold text-savo-purple">{p.code}</span>
                  <StageBadge stage={p.stage} />
                </div>
                <div className="truncate font-semibold text-slate-900">{p.name}</div>
                <div className="text-xs text-slate-500">updated {ago(p.updated_at)}</div>
                <FlagChips flags={p.flags.filter((f) => f.severity !== "low")} />
              </div>
              <div className="text-right">
                {p.latest_score !== null && <div className="text-lg font-bold">{Math.round(p.latest_score)}</div>}
                <RecPill rec={p.latest_recommendation} />
              </div>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
