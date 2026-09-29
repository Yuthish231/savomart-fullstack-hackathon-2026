import { useState } from "react";
import { useCreateTask, useTeam } from "@/api/properties";
import type { Hotspot } from "@/api/areas";
import { Button, ErrorNote } from "@/components/ui";
import { Modal } from "@/components/property";

/** BD Manager directs an executive to scout a hotspot (or the whole area). */
export function AssignTask({ reportId, hotspot, onClose }: { reportId: string; hotspot: Hotspot | null; onClose: () => void }) {
  const team = useTeam("BDE");
  const create = useCreateTask();
  const [assignee, setAssignee] = useState("");
  const [note, setNote] = useState("");
  const [due, setDue] = useState("");

  return (
    <Modal title={hotspot ? `Scout hotspot ${hotspot.rank}` : "Scout this area"} onClose={onClose}>
      {hotspot && (
        <p className="text-sm text-slate-600">
          {hotspot.near_road ?? "Unnamed streets"} · score {Math.round(hotspot.score)} · {hotspot.nearest_store_km} km from Savomart
        </p>
      )}
      <fieldset className="mt-3">
        <legend className="text-sm font-semibold text-slate-700">BD Executive</legend>
        <div className="mt-1 space-y-1">
          {team.data?.map((u) => (
            <label key={u.id} className="flex cursor-pointer items-center justify-between rounded-lg border border-slate-200 px-3 py-2 text-sm has-[:checked]:border-savo-purple has-[:checked]:bg-savo-purple-light">
              <span className="flex items-center gap-2">
                <input type="radio" name="assignee" className="accent-savo-purple" value={u.id} checked={assignee === u.id} onChange={() => setAssignee(u.id)} />
                {u.name}
              </span>
              <span className="text-xs text-slate-500">{u.open_tasks} open task{u.open_tasks === 1 ? "" : "s"}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <label className="mt-3 block text-sm font-semibold text-slate-700">
        Note
        <textarea className="mt-1 min-h-16 w-full rounded-lg border border-slate-300 p-2 text-sm font-normal focus:border-savo-purple focus:outline-none"
          placeholder="e.g. Ground-floor shops on the main road, 1,500+ sq ft" value={note} onChange={(e) => setNote(e.target.value)} />
      </label>
      <label className="mt-2 block text-sm font-semibold text-slate-700">
        Due
        <input type="date" className="mt-1 block rounded-lg border border-slate-300 px-2 py-1.5 text-sm font-normal" value={due} onChange={(e) => setDue(e.target.value)} />
      </label>
      {create.error && <div className="mt-2"><ErrorNote error={create.error} /></div>}
      <div className="mt-4 flex justify-end gap-2">
        <Button variant="ghost" onClick={onClose}>Cancel</Button>
        <Button disabled={!assignee} loading={create.isPending}
          onClick={() => create.mutate({ report_id: reportId, hotspot_id: hotspot?.id ?? null, assignee_id: assignee, note: note || undefined, due_date: due || null }, { onSuccess: onClose })}>
          Assign
        </Button>
      </div>
    </Modal>
  );
}
