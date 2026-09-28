import { Hammer } from "lucide-react";
import { EmptyState, PageHeader } from "@/components/ui";

/** Temporary screen for routes whose milestone is not built yet. */
export function Placeholder({
  title,
  subtitle,
  milestone,
  body,
}: {
  title: string;
  subtitle?: string;
  milestone: string;
  body: string;
}) {
  return (
    <div className="mx-auto max-w-5xl p-4 md:p-6">
      <PageHeader title={title} subtitle={subtitle} />
      <EmptyState icon={<Hammer className="h-5 w-5" />} title={`Arriving with ${milestone}`} body={body} />
    </div>
  );
}
