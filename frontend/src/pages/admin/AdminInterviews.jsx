import { useState, useEffect, useCallback, useMemo } from "react";
import api, { formatApiError } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import {
  AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription,
  AlertDialogFooter, AlertDialogCancel, AlertDialogAction,
} from "@/components/ui/alert-dialog";
import VideoCall from "@/components/VideoCall";
import { Checkbox } from "@/components/ui/checkbox";
import { useListControls } from "@/hooks/useListControls";
import { ListToolbar } from "@/components/ListControls";
import { CalendarDays, ChevronLeft, ChevronRight, Video, Plus, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";

const EMPTY_ITW = { title: "", candidate_id: "", candidate_name: "", date: "", time: "", location: "", notes: "", status: "scheduled" };

const DAYN = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"];
const isoLocal = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
function startOfWeek(offset) {
  const now = new Date();
  const day = (now.getDay() + 6) % 7; // Monday = 0
  return new Date(now.getFullYear(), now.getMonth(), now.getDate() - day + offset * 7);
}

function WeekAgenda({ list, offset, setOffset, onJoin, onEdit }) {
  const monday = startOfWeek(offset);
  const days = Array.from({ length: 7 }, (_, k) => { const d = new Date(monday); d.setDate(monday.getDate() + k); return d; });
  const todayIso = isoLocal(new Date());
  const label = `${monday.toLocaleDateString("fr-FR", { day: "numeric", month: "short" })} — ${days[6].toLocaleDateString("fr-FR", { day: "numeric", month: "short", year: "numeric" })}`;
  return (
    <div data-testid="week-agenda">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Button variant="outline" size="icon" className="rounded-full h-8 w-8" onClick={() => setOffset(offset - 1)} data-testid="week-prev"><ChevronLeft className="h-4 w-4" /></Button>
          <Button variant="outline" size="sm" className="rounded-full" onClick={() => setOffset(0)} data-testid="week-today">Aujourd'hui</Button>
          <Button variant="outline" size="icon" className="rounded-full h-8 w-8" onClick={() => setOffset(offset + 1)} data-testid="week-next"><ChevronRight className="h-4 w-4" /></Button>
        </div>
        <span className="text-sm font-medium text-muted-foreground">{label}</span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-7 gap-3">
        {days.map((d, k) => {
          const iso = isoLocal(d);
          const items = list.filter((i) => i.date === iso).sort((a, b) => a.time.localeCompare(b.time));
          const isToday = iso === todayIso;
          return (
            <div key={iso} className={`rounded-xl border ${isToday ? "border-primary" : "border-border"} bg-card min-h-[120px]`} data-testid={`week-day-${iso}`}>
              <div className={`px-3 py-2 border-b text-center ${isToday ? "bg-primary/10 border-primary/30" : "border-border bg-secondary/40"}`}>
                <div className="text-xs text-muted-foreground">{DAYN[k]}</div>
                <div className={`font-display font-semibold ${isToday ? "text-primary" : ""}`}>{d.getDate()}</div>
              </div>
              <div className="p-2 space-y-2">
                {items.length === 0 ? <p className="text-[11px] text-muted-foreground/50 text-center py-2">—</p> : items.map((i) => (
                  <button key={i.id} onClick={() => onEdit(i)} data-testid={`week-itw-${i.id}`} className="w-full text-left rounded-lg bg-primary/10 hover:bg-primary/20 transition-colors p-2">
                    <div className="font-mono text-xs font-semibold text-primary">{i.time}</div>
                    <div className="text-xs font-medium truncate">{i.title}</div>
                    <div className="text-[11px] text-muted-foreground truncate">{i.candidate_name}</div>
                    <span onClick={(e) => { e.stopPropagation(); onJoin(i); }} className="inline-flex items-center gap-1 text-[11px] text-primary mt-1 hover:underline" data-testid={`week-join-${i.id}`}><Video className="h-3 w-3" /> Rejoindre</span>
                  </button>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function Interviews() {
  const [list, setList] = useState([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_ITW);
  const [del, setDel] = useState(null);
  const [call, setCall] = useState(null);
  const [candidates, setCandidates] = useState([]);
  const [view, setView] = useState("week");
  const [weekOffset, setWeekOffset] = useState(0);
  const [search, setSearch] = useState("");
  const load = useCallback(() => api.get(`/interviews`).then(({ data }) => setList(data)).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { api.get(`/candidates`).then(({ data }) => setCandidates(data)).catch(() => {}); }, []);
  const openNew = () => { setEditing(null); setForm(EMPTY_ITW); setOpen(true); };
  const openEdit = (i) => { setEditing(i); setForm({ ...EMPTY_ITW, ...i }); setOpen(true); };
  const save = async () => {
    try {
      if (editing) await api.put(`/interviews/${editing.id}`, form);
      else await api.post(`/interviews`, form);
      toast.success(editing ? "Entretien mis à jour" : "Entretien planifié");
      setOpen(false); load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const remove = async () => { await api.delete(`/interviews/${del.id}`); toast.success("Entretien supprimé"); setDel(null); load(); };

  const filtered = useMemo(() => list.filter((i) => { const q = search.trim().toLowerCase(); return !q || [i.title, i.candidate_name, i.location].some((v) => (v || "").toLowerCase().includes(q)); }), [list, search]);
  const groups = useMemo(() => filtered.reduce((acc, i) => { (acc[i.date] = acc[i.date] || []).push(i); return acc; }, {}), [filtered]);
  const dates = useMemo(() => Object.keys(groups).sort(), [groups]);
  const lc = useListControls(filtered, { pageSize: 9999, selectId: (i) => i.id });
  const bulkDelete = async () => {
    const ids = lc.selectedIds();
    if (ids.length === 0) return;
    if (!window.confirm(`Supprimer ${ids.length} entretien(s) ?`)) return;
    await Promise.all(ids.map((id) => api.delete(`/interviews/${id}`).catch(() => {})));
    toast.success("Suppression effectuée");
    lc.clear(); load();
  };
  const fmtDate = (d) => { try { return new Date(d + "T00:00:00").toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric" }); } catch { return d; } };

  return (
    <div>
      {call && <VideoCall room={call.room} audioOnly={call.audioOnly} title={`Entretien`} onClose={() => setCall(null)} />}
      <div className="flex items-center justify-between mb-6 gap-3 flex-wrap">
        <div>
          <h1 className="font-display text-3xl font-semibold">Agenda des entretiens</h1>
          <p className="text-muted-foreground text-sm">{list.length} entretien{list.length > 1 ? "s" : ""} planifié{list.length > 1 ? "s" : ""}</p>
        </div>
        <div className="flex items-center gap-2">
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Rechercher (intitulé, candidat, lieu...)" className="w-56 rounded-full" data-testid="interview-search-input" />
          <div className="inline-flex rounded-full border border-border p-0.5">
            <button onClick={() => setView("week")} data-testid="agenda-view-week" className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${view === "week" ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}>Semaine</button>
            <button onClick={() => setView("list")} data-testid="agenda-view-list" className={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${view === "list" ? "bg-primary text-primary-foreground" : "text-muted-foreground"}`}>Liste</button>
          </div>
          <Button onClick={openNew} className="rounded-full" data-testid="new-interview-btn"><Plus className="h-4 w-4 mr-2" /> Planifier</Button>
        </div>
      </div>

      {view === "week" ? (
        <WeekAgenda list={filtered} offset={weekOffset} setOffset={setWeekOffset} onJoin={(i) => setCall({ room: `recrutai-itw-${i.id}`, audioOnly: false })} onEdit={openEdit} />
      ) : dates.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-16 text-center text-muted-foreground">
          <CalendarDays className="h-12 w-12 text-muted-foreground/40 mx-auto mb-4" />
          Aucun entretien planifié.
        </div>
      ) : (
        <>
        <ListToolbar lc={lc} onBulkDelete={bulkDelete} testId="interviews" showPager={false} />
        <div className="space-y-6">
          {dates.map((d) => (
            <div key={d} className="rounded-2xl border border-border bg-card overflow-hidden">
              <div className="flex items-center justify-between px-5 py-3 border-b border-border bg-secondary/40">
                <span className="font-display font-semibold capitalize">{fmtDate(d)}</span>
                <span className="rounded-full bg-primary/15 text-primary px-2.5 py-0.5 text-xs font-semibold">{groups[d].length} entretien{groups[d].length > 1 ? "s" : ""}</span>
              </div>
              <div className="divide-y divide-border">
                {groups[d].sort((a, b) => a.time.localeCompare(b.time)).map((i) => (
                  <div key={i.id} className="flex items-center gap-4 px-5 py-3" data-testid={`interview-row-${i.id}`}>
                    {lc.selectMode && <Checkbox checked={lc.selected.has(i.id)} onCheckedChange={() => lc.toggle(i.id)} data-testid={`select-interview-${i.id}`} />}
                    <span className="font-mono font-semibold text-primary w-14">{i.time}</span>
                    <div className="flex-1">
                      <p className="font-medium">{i.title}</p>
                      <p className="text-xs text-muted-foreground">{[i.candidate_name, i.location].filter(Boolean).join(" • ")}</p>
                    </div>
                    <Button variant="outline" size="sm" className="rounded-full" onClick={() => setCall({ room: `recrutai-itw-${i.id}`, audioOnly: false })} data-testid={`join-interview-${i.id}`}><Video className="h-4 w-4 mr-1" /> Rejoindre</Button>
                    <Button variant="ghost" size="icon" onClick={() => openEdit(i)} data-testid={`edit-interview-${i.id}`}><Pencil className="h-4 w-4" /></Button>
                    <Button variant="ghost" size="icon" onClick={() => setDel(i)} data-testid={`delete-interview-${i.id}`}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
        </>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>{editing ? "Modifier l'entretien" : "Nouvel entretien"}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>Intitulé</Label><Input data-testid="interview-title-input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="mt-1" placeholder="Ex : Entretien technique" /></div>
            <div><Label>Candidat</Label>
              <Select value={form.candidate_id || ""} onValueChange={(v) => { const c = candidates.find((x) => x.user_id === v); setForm({ ...form, candidate_id: v, candidate_name: c?.name || "" }); }}>
                <SelectTrigger className="mt-1" data-testid="interview-candidate-select"><SelectValue placeholder="Sélectionner un candidat" /></SelectTrigger>
                <SelectContent>
                  {candidates.map((c) => (<SelectItem key={c.user_id} value={c.user_id}>{c.name} — {c.email}</SelectItem>))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Date</Label><Input type="date" data-testid="interview-date-input" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} className="mt-1" /></div>
              <div><Label>Heure</Label><Input type="time" data-testid="interview-time-input" value={form.time} onChange={(e) => setForm({ ...form, time: e.target.value })} className="mt-1" /></div>
            </div>
            <div><Label>Lieu / Lien visio</Label><Input value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} className="mt-1" /></div>
            <div><Label>Notes</Label><Textarea rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} className="mt-1" /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} className="rounded-full">Annuler</Button>
            <Button onClick={save} disabled={!form.title || !form.date || !form.time} className="rounded-full" data-testid="save-interview-btn">Enregistrer</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!del} onOpenChange={() => setDel(null)}>
        <AlertDialogContent>
          <AlertDialogHeader><AlertDialogTitle>Supprimer cet entretien ?</AlertDialogTitle><AlertDialogDescription>Action irréversible.</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter><AlertDialogCancel>Annuler</AlertDialogCancel><AlertDialogAction onClick={remove} data-testid="confirm-delete-interview">Supprimer</AlertDialogAction></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
