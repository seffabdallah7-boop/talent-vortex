import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import api, { fileUrl, formatApiError, API } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useTheme } from "@/context/ThemeContext";
import { useDarkMode } from "@/context/DarkModeContext";
import StatusBadge from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import {
  AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription,
  AlertDialogFooter, AlertDialogCancel, AlertDialogAction,
} from "@/components/ui/alert-dialog";
import {
  LayoutGrid, Briefcase, Users, FileText, MessageSquare, Palette, Plus, Trash2, Pencil,
  LogOut, Volume2, Send, Loader2, Building2, CheckCircle2, Sun, Moon,
  CalendarDays, ScrollText, Download, Star, Video, Phone,
} from "lucide-react";
import { toast } from "sonner";
import VideoCall from "@/components/VideoCall";

const NAV = [
  { key: "overview", label: "Tableau de bord", Icon: LayoutGrid },
  { key: "jobs", label: "Offres d'emploi", Icon: Briefcase },
  { key: "applications", label: "Candidatures", Icon: FileText },
  { key: "contracts", label: "Contrats", Icon: ScrollText },
  { key: "interviews", label: "Agenda entretiens", Icon: CalendarDays },
  { key: "candidates", label: "Utilisateurs", Icon: Users },
  { key: "messages", label: "Messages", Icon: MessageSquare },
  { key: "theme", label: "Apparence", Icon: Palette },
];

const PRESETS = [
  { name: "Bleu Corporate", primary: "220 100% 33%", fg: "0 0% 100%" },
  { name: "Vert Émeraude", primary: "160 84% 30%", fg: "0 0% 100%" },
  { name: "Violet Royal", primary: "265 70% 45%", fg: "0 0% 100%" },
  { name: "Orange Ambre", primary: "25 95% 45%", fg: "0 0% 100%" },
  { name: "Rose Fuchsia", primary: "330 75% 45%", fg: "0 0% 100%" },
  { name: "Noir Ardoise", primary: "240 6% 16%", fg: "0 0% 100%" },
];

function hexToHsl(hex) {
  let r = parseInt(hex.slice(1, 3), 16) / 255;
  let g = parseInt(hex.slice(3, 5), 16) / 255;
  let b = parseInt(hex.slice(5, 7), 16) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b);
  let h, s, l = (max + min) / 2;
  if (max === min) { h = s = 0; }
  else {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r: h = (g - b) / d + (g < b ? 6 : 0); break;
      case g: h = (b - r) / d + 2; break;
      default: h = (r - g) / d + 4;
    }
    h /= 6;
  }
  return `${Math.round(h * 360)} ${Math.round(s * 100)}% ${Math.round(l * 100)}%`;
}

export default function AdminDashboard() {
  const { user, logout } = useAuth();
  const { dark, toggle } = useDarkMode();
  const navigate = useNavigate();
  const [section, setSection] = useState("overview");

  return (
    <div className="min-h-screen flex bg-background">
      <aside className="w-64 shrink-0 border-r border-border bg-card hidden md:flex flex-col">
        <div className="h-16 flex items-center gap-2.5 px-5 border-b border-border">
          <div className="h-9 w-9 rounded-lg bg-primary flex items-center justify-center">
            <Briefcase className="h-5 w-5 text-primary-foreground" />
          </div>
          <span className="font-display text-lg font-semibold">Talent Vortex</span>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          {NAV.map((n) => (
            <button
              key={n.key}
              onClick={() => setSection(n.key)}
              data-testid={`nav-${n.key}`}
              className={`w-full flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${section === n.key ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-secondary"}`}
            >
              <n.Icon className="h-4.5 w-4.5" /> {n.label}
            </button>
          ))}
        </nav>
        <div className="p-3 border-t border-border space-y-2">
          <div className="flex items-center justify-between px-1">
            <p className="text-xs text-muted-foreground truncate">{user?.email}</p>
            <button
              onClick={toggle}
              data-testid="admin-dark-toggle"
              aria-label="Basculer le thème"
              className="h-8 w-8 shrink-0 rounded-full border border-border flex items-center justify-center hover:bg-secondary transition-colors"
            >
              {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
          </div>
          <Button variant="outline" className="w-full rounded-lg" onClick={() => { logout(); navigate("/"); }} data-testid="admin-logout-btn">
            <LogOut className="h-4 w-4 mr-2" /> Déconnexion
          </Button>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">
        <div className="md:hidden flex gap-2 p-3 overflow-x-auto border-b border-border">
          {NAV.map((n) => (
            <button key={n.key} onClick={() => setSection(n.key)} className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-medium ${section === n.key ? "bg-primary text-primary-foreground" : "bg-secondary"}`}>{n.label}</button>
          ))}
        </div>
        <div className="p-6 md:p-8 max-w-6xl">
          {section === "overview" && <Overview />}
          {section === "jobs" && <Jobs />}
          {section === "applications" && <Applications />}
          {section === "contracts" && <Contracts />}
          {section === "interviews" && <Interviews />}
          {section === "candidates" && <Candidates />}
          {section === "messages" && <Messages />}
          {section === "theme" && <ThemeSection />}
        </div>
      </main>
    </div>
  );
}

function Overview() {
  const [stats, setStats] = useState(null);
  useEffect(() => { api.get("/admin/stats").then(({ data }) => setStats(data)).catch(() => {}); }, []);
  if (!stats) return <Loader2 className="h-6 w-6 animate-spin text-primary" />;
  const cards = [
    { label: "Offres actives", value: stats.active_jobs, Icon: Briefcase },
    { label: "Candidats", value: stats.candidates, Icon: Users },
    { label: "Candidatures", value: stats.applications, Icon: FileText },
    { label: "En attente", value: stats.pending, Icon: CheckCircle2 },
    { label: "Contrats actifs", value: stats.contracts_active, Icon: ScrollText },
    { label: "Entretiens à venir", value: stats.upcoming_interviews, Icon: CalendarDays },
  ];
  return (
    <div>
      <h1 className="font-display text-3xl font-semibold mb-6">Tableau de bord</h1>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {cards.map((c) => (
          <div key={c.label} className="rounded-2xl border border-border bg-card p-5" data-testid={`stat-${c.label}`}>
            <c.Icon className="h-5 w-5 text-primary mb-3" />
            <p className="font-display text-3xl font-semibold">{c.value}</p>
            <p className="text-sm text-muted-foreground">{c.label}</p>
          </div>
        ))}
      </div>
      <div className="grid grid-cols-3 gap-4">
        <div className="rounded-2xl border status-pending p-5"><p className="font-display text-2xl font-semibold">{stats.pending}</p><p className="text-sm">En attente</p></div>
        <div className="rounded-2xl border status-accepted p-5"><p className="font-display text-2xl font-semibold">{stats.accepted}</p><p className="text-sm">Acceptées</p></div>
        <div className="rounded-2xl border status-rejected p-5"><p className="font-display text-2xl font-semibold">{stats.rejected}</p><p className="text-sm">Refusées</p></div>
      </div>
    </div>
  );
}

const EMPTY_JOB = { title: "", company: "", location: "", type: "Temps plein", category: "General", description: "", requirements: "", salary: "" };

function Jobs() {
  const [jobs, setJobs] = useState([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_JOB);
  const [saving, setSaving] = useState(false);
  const [del, setDel] = useState(null);

  const load = useCallback(() => api.get("/jobs/all").then(({ data }) => setJobs(data)).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);

  const openNew = () => { setEditing(null); setForm(EMPTY_JOB); setOpen(true); };
  const openEdit = (j) => { setEditing(j); setForm({ ...EMPTY_JOB, ...j }); setOpen(true); };

  const save = async () => {
    setSaving(true);
    try {
      const payload = { title: form.title, company: form.company, location: form.location, type: form.type, category: form.category, description: form.description, requirements: form.requirements, salary: form.salary };
      if (editing) await api.put(`/jobs/${editing.id}`, payload);
      else await api.post("/jobs", payload);
      toast.success(editing ? "Offre mise à jour" : "Offre publiée");
      setOpen(false); load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setSaving(false); }
  };

  const remove = async () => { await api.delete(`/jobs/${del.id}`); toast.success("Offre supprimée"); setDel(null); load(); };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="font-display text-3xl font-semibold">Offres d'emploi</h1>
        <Button onClick={openNew} className="rounded-full" data-testid="new-job-btn"><Plus className="h-4 w-4 mr-2" /> Publier une offre</Button>
      </div>

      {jobs.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-16 text-center">
          <Briefcase className="h-12 w-12 text-muted-foreground/40 mx-auto mb-4" />
          <p className="text-muted-foreground mb-5">Aucune offre publiée.</p>
          <Button onClick={openNew} className="rounded-full"><Plus className="h-4 w-4 mr-2" /> Publier votre première offre</Button>
        </div>
      ) : (
        <div className="rounded-2xl border border-border bg-card overflow-hidden">
          <Table>
            <TableHeader><TableRow><TableHead>Poste</TableHead><TableHead>Lieu</TableHead><TableHead>Candidats</TableHead><TableHead className="text-right">Actions</TableHead></TableRow></TableHeader>
            <TableBody>
              {jobs.map((j) => (
                <TableRow key={j.id} data-testid={`job-row-${j.id}`}>
                  <TableCell><div className="font-medium">{j.title}</div><div className="text-xs text-muted-foreground">{j.company}</div></TableCell>
                  <TableCell>{j.location}</TableCell>
                  <TableCell><span className="rounded-full bg-secondary px-2.5 py-0.5 text-xs font-medium">{j.applicants || 0}</span></TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="icon" onClick={() => openEdit(j)} data-testid={`edit-job-${j.id}`}><Pencil className="h-4 w-4" /></Button>
                    <Button variant="ghost" size="icon" onClick={() => setDel(j)} data-testid={`delete-job-${j.id}`}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editing ? "Modifier l'offre" : "Nouvelle offre"}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>Intitulé du poste</Label><Input data-testid="job-title-input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="mt-1" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Entreprise</Label><Input data-testid="job-company-input" value={form.company} onChange={(e) => setForm({ ...form, company: e.target.value })} className="mt-1" /></div>
              <div><Label>Lieu</Label><Input data-testid="job-location-input" value={form.location} onChange={(e) => setForm({ ...form, location: e.target.value })} className="mt-1" /></div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div><Label>Type</Label><Input value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} className="mt-1" /></div>
              <div><Label>Catégorie</Label><Input value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} className="mt-1" /></div>
              <div><Label>Salaire</Label><Input value={form.salary} onChange={(e) => setForm({ ...form, salary: e.target.value })} className="mt-1" /></div>
            </div>
            <div><Label>Description</Label><Textarea data-testid="job-description-input" rows={4} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} className="mt-1" /></div>
            <div><Label>Profil recherché</Label><Textarea rows={3} value={form.requirements} onChange={(e) => setForm({ ...form, requirements: e.target.value })} className="mt-1" /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} className="rounded-full">Annuler</Button>
            <Button onClick={save} disabled={saving || !form.title} className="rounded-full" data-testid="save-job-btn">{saving ? <Loader2 className="h-4 w-4 animate-spin" /> : "Enregistrer"}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!del} onOpenChange={() => setDel(null)}>
        <AlertDialogContent>
          <AlertDialogHeader><AlertDialogTitle>Supprimer cette offre ?</AlertDialogTitle><AlertDialogDescription>Cette action est irréversible.</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter><AlertDialogCancel>Annuler</AlertDialogCancel><AlertDialogAction onClick={remove} data-testid="confirm-delete-job">Supprimer</AlertDialogAction></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function Applications() {
  const [apps, setApps] = useState([]);
  const [filter, setFilter] = useState("all");
  const [detail, setDetail] = useState(null);
  const [del, setDel] = useState(null);
  const [note, setNote] = useState("");
  const [rating, setRating] = useState(0);

  const load = useCallback(() => api.get(`/applications?status=${filter}`).then(({ data }) => setApps(data)).catch(() => {}), [filter]);
  useEffect(() => { load(); }, [load]);

  const setStatus = async (id, status) => {
    await api.put(`/applications/${id}/status`, { status });
    toast.success("Statut mis à jour");
    setDetail((d) => (d && d.id === id ? { ...d, status } : d));
    load();
  };
  const remove = async () => { await api.delete(`/applications/${del.id}`); toast.success("Candidature supprimée"); setDel(null); setDetail(null); load(); };
  const saveReview = async () => {
    try {
      const { data } = await api.put(`/applications/${detail.id}/review`, { admin_note: note, rating: rating || null });
      toast.success("Évaluation enregistrée");
      setDetail(data); load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6 gap-3 flex-wrap">
        <h1 className="font-display text-3xl font-semibold">Candidatures</h1>
        <div className="flex items-center gap-2">
          <Button asChild variant="outline" className="rounded-full" data-testid="export-applications-btn">
            <a href={`${API}/export/applications?auth=${encodeURIComponent(localStorage.getItem("token") || "")}`}><Download className="h-4 w-4 mr-2" /> Export CSV</a>
          </Button>
          <Select value={filter} onValueChange={setFilter}>
            <SelectTrigger className="w-44 rounded-full" data-testid="status-filter"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Toutes</SelectItem>
              <SelectItem value="pending">En attente</SelectItem>
              <SelectItem value="accepted">Acceptées</SelectItem>
              <SelectItem value="rejected">Refusées</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {apps.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-16 text-center text-muted-foreground">Aucune candidature.</div>
      ) : (
        <div className="rounded-2xl border border-border bg-card overflow-hidden">
          <Table>
            <TableHeader><TableRow><TableHead>Candidat</TableHead><TableHead>Poste</TableHead><TableHead>Statut</TableHead><TableHead className="text-right">Action</TableHead></TableRow></TableHeader>
            <TableBody>
              {apps.map((a) => (
                <TableRow key={a.id} className="cursor-pointer" onClick={() => setDetail(a)} data-testid={`app-row-${a.id}`}>
                  <TableCell><div className="font-medium">{a.candidate_name}</div><div className="text-xs text-muted-foreground">{a.candidate_email}</div></TableCell>
                  <TableCell>{a.job_title}</TableCell>
                  <TableCell><StatusBadge status={a.status} /></TableCell>
                  <TableCell className="text-right"><Button variant="outline" size="sm" className="rounded-full">Examiner</Button></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <Dialog open={!!detail} onOpenChange={() => setDetail(null)}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          {detail && (
            <>
              <DialogHeader><DialogTitle>{detail.candidate_name}</DialogTitle></DialogHeader>
              <div className="space-y-4">
                <div className="flex items-center gap-2">
                  <StatusBadge status={detail.status} />
                  <span className="text-sm text-muted-foreground">• {detail.job_title}</span>
                </div>
                <p className="text-sm text-muted-foreground">{detail.candidate_email}</p>
                {detail.cover_note && <div className="rounded-lg bg-secondary/50 p-3"><p className="text-xs font-semibold mb-1">Note de motivation</p><p className="text-sm italic">"{detail.cover_note}"</p></div>}
                {detail.transcription && <div className="rounded-lg bg-secondary/50 p-3"><p className="text-xs font-semibold mb-1">Transcription du message vocal</p><p className="text-sm">{detail.transcription}</p></div>}
                <div className="flex flex-wrap gap-2">
                  {detail.cv_file_id && <Button asChild variant="outline" size="sm" className="rounded-full" data-testid="admin-view-cv"><a href={fileUrl(detail.cv_file_id)} target="_blank" rel="noreferrer"><FileText className="h-4 w-4 mr-2" /> Voir le CV</a></Button>}
                  {detail.voice_file_id && <Button asChild variant="outline" size="sm" className="rounded-full" data-testid="admin-play-voice"><a href={fileUrl(detail.voice_file_id)} target="_blank" rel="noreferrer"><Volume2 className="h-4 w-4 mr-2" /> Écouter le vocal</a></Button>}
                </div>
                <div className="border-t border-border pt-4">
                  <p className="text-xs font-semibold text-muted-foreground mb-2">Évaluation interne (admin)</p>
                  <div className="flex items-center gap-1 mb-3">
                    {[1, 2, 3, 4, 5].map((n) => (
                      <button key={n} type="button" onClick={() => setRating(n)} data-testid={`rating-${n}`}>
                        <Star className={`h-6 w-6 ${n <= rating ? "fill-primary text-primary" : "text-muted-foreground"}`} />
                      </button>
                    ))}
                  </div>
                  <Textarea data-testid="admin-note-input" rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Note interne sur le candidat..." />
                  <Button size="sm" className="rounded-full mt-2" onClick={saveReview} data-testid="save-review-btn">Enregistrer l'évaluation</Button>
                </div>
                <div className="border-t border-border pt-4">
                  <p className="text-xs font-semibold text-muted-foreground mb-2">Décision</p>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" onClick={() => setStatus(detail.id, "accepted")} className="rounded-full status-accepted border-0" data-testid="accept-btn">Accepter</Button>
                    <Button size="sm" onClick={() => setStatus(detail.id, "rejected")} className="rounded-full status-rejected border-0" data-testid="reject-btn">Refuser</Button>
                    <Button size="sm" variant="outline" onClick={() => setStatus(detail.id, "pending")} className="rounded-full">En attente</Button>
                    <Button size="sm" variant="ghost" onClick={() => setDel(detail)} className="rounded-full ml-auto text-destructive" data-testid="delete-app-btn"><Trash2 className="h-4 w-4" /></Button>
                  </div>
                </div>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!del} onOpenChange={() => setDel(null)}>
        <AlertDialogContent>
          <AlertDialogHeader><AlertDialogTitle>Supprimer cette candidature ?</AlertDialogTitle><AlertDialogDescription>Action irréversible.</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter><AlertDialogCancel>Annuler</AlertDialogCancel><AlertDialogAction onClick={remove} data-testid="confirm-delete-app">Supprimer</AlertDialogAction></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function Candidates() {
  const { user: me } = useAuth();
  const [list, setList] = useState([]);
  const [del, setDel] = useState(null);
  const load = useCallback(() => api.get("/users").then(({ data }) => setList(data)).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);
  const remove = async () => {
    try {
      await api.delete(`/users/${del.user_id}`);
      toast.success("Utilisateur supprimé");
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    setDel(null); load();
  };
  const changeRole = async (u, role) => {
    try {
      await api.put(`/users/${u.user_id}/role`, { role });
      toast.success(role === "admin" ? `${u.name} est maintenant administrateur` : `${u.name} est de nouveau candidat`);
      load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  return (
    <div>
      <h1 className="font-display text-3xl font-semibold mb-2">Utilisateurs & rôles</h1>
      <p className="text-muted-foreground mb-6">Gérez les comptes : promouvoir en administrateur, rétrograder en candidat, ou supprimer.</p>
      {list.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-16 text-center text-muted-foreground">Aucun utilisateur.</div>
      ) : (
        <div className="rounded-2xl border border-border bg-card overflow-hidden">
          <Table>
            <TableHeader><TableRow><TableHead>Nom</TableHead><TableHead>Email</TableHead><TableHead>Rôle</TableHead><TableHead>Candidatures</TableHead><TableHead className="text-right">Actions</TableHead></TableRow></TableHeader>
            <TableBody>
              {list.map((u) => {
                const isSelf = me && u.user_id === me.user_id;
                return (
                  <TableRow key={u.user_id} data-testid={`candidate-row-${u.user_id}`}>
                    <TableCell className="font-medium">{u.name} {isSelf && <span className="text-xs text-muted-foreground">(vous)</span>}</TableCell>
                    <TableCell className="text-muted-foreground">{u.email}</TableCell>
                    <TableCell>
                      <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${u.role === "admin" ? "bg-primary/15 text-primary" : "bg-secondary text-muted-foreground"}`}>
                        {u.role === "admin" ? "Administrateur" : "Candidat"}
                      </span>
                    </TableCell>
                    <TableCell><span className="rounded-full bg-secondary px-2.5 py-0.5 text-xs font-medium">{u.application_count}</span></TableCell>
                    <TableCell className="text-right">
                      {!isSelf && u.role === "candidate" && (
                        <Button variant="outline" size="sm" className="rounded-full mr-2" onClick={() => changeRole(u, "admin")} data-testid={`promote-${u.user_id}`}>Promouvoir admin</Button>
                      )}
                      {!isSelf && u.role === "admin" && (
                        <Button variant="outline" size="sm" className="rounded-full mr-2" onClick={() => changeRole(u, "candidate")} data-testid={`demote-${u.user_id}`}>Rétrograder</Button>
                      )}
                      {!isSelf && (
                        <Button variant="ghost" size="icon" onClick={() => setDel(u)} data-testid={`delete-candidate-${u.user_id}`}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                      )}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </div>
      )}
      <AlertDialog open={!!del} onOpenChange={() => setDel(null)}>
        <AlertDialogContent>
          <AlertDialogHeader><AlertDialogTitle>Supprimer {del?.name} ?</AlertDialogTitle><AlertDialogDescription>L'utilisateur et toutes ses candidatures seront supprimés définitivement.</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter><AlertDialogCancel>Annuler</AlertDialogCancel><AlertDialogAction onClick={remove} data-testid="confirm-delete-candidate">Supprimer</AlertDialogAction></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function Messages() {
  const [convs, setConvs] = useState([]);
  const [active, setActive] = useState(null);
  const [msgs, setMsgs] = useState([]);
  const [text, setText] = useState("");
  const [call, setCall] = useState(null);

  useEffect(() => {
    const load = () => api.get("/chat/conversations").then(({ data }) => setConvs(data)).catch(() => {});
    load();
    const int = setInterval(load, 5000);
    return () => clearInterval(int);
  }, []);

  useEffect(() => {
    if (!active) return;
    const load = () => api.get(`/chat/messages?candidate_id=${active.candidate_id}`).then(({ data }) => setMsgs(data)).catch(() => {});
    load();
    const int = setInterval(load, 4000);
    return () => clearInterval(int);
  }, [active]);

  const send = async () => {
    if (!text.trim() || !active) return;
    const { data } = await api.post("/chat/messages", { text: text.trim(), candidate_id: active.candidate_id });
    setMsgs((m) => [...m, data]);
    setText("");
  };

  return (
    <div>
      {call && <VideoCall room={call.room} audioOnly={call.audioOnly} onClose={() => setCall(null)} />}
      <h1 className="font-display text-3xl font-semibold mb-6">Messages</h1>
      <div className="grid md:grid-cols-3 gap-4 h-[560px]">
        <div className="rounded-2xl border border-border bg-card overflow-y-auto">
          {convs.length === 0 ? <p className="p-6 text-sm text-muted-foreground">Aucune conversation.</p> : convs.map((c) => (
            <button key={c.candidate_id} onClick={() => setActive(c)} data-testid={`conv-${c.candidate_id}`} className={`w-full text-left p-4 border-b border-border hover:bg-secondary transition-colors ${active?.candidate_id === c.candidate_id ? "bg-secondary" : ""}`}>
              <div className="flex items-center justify-between">
                <span className="font-medium text-sm">{c.candidate_name || "Candidat"}</span>
                {c.unread > 0 && <span className="h-5 min-w-5 px-1 rounded-full bg-primary text-primary-foreground text-xs flex items-center justify-center">{c.unread}</span>}
              </div>
              <p className="text-xs text-muted-foreground truncate mt-1">{c.last_text}</p>
            </button>
          ))}
        </div>
        <div className="md:col-span-2 rounded-2xl border border-border bg-card flex flex-col">
          {!active ? (
            <div className="flex-1 flex items-center justify-center text-muted-foreground text-sm">Sélectionnez une conversation</div>
          ) : (
            <>
              <div className="p-4 border-b border-border font-medium flex items-center justify-between">
                <span>{active.candidate_name || "Candidat"}</span>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" className="rounded-full" onClick={() => setCall({ room: `recrutai-chat-${active.candidate_id}`, audioOnly: false })} data-testid="admin-video-call-btn"><Video className="h-4 w-4" /></Button>
                  <Button size="sm" variant="outline" className="rounded-full" onClick={() => setCall({ room: `recrutai-chat-${active.candidate_id}`, audioOnly: true })} data-testid="admin-audio-call-btn"><Phone className="h-4 w-4" /></Button>
                </div>
              </div>
              <div className="flex-1 overflow-y-auto p-4 space-y-2">
                {msgs.map((m) => (
                  <div key={m.id} className={`flex ${m.sender_role === "admin" ? "justify-end" : "justify-start"}`}>
                    <div className={`max-w-[75%] rounded-2xl px-3.5 py-2 text-sm ${m.sender_role === "admin" ? "bg-primary text-primary-foreground" : "bg-secondary"}`}>{m.text}</div>
                  </div>
                ))}
              </div>
              <div className="p-3 border-t border-border flex gap-2">
                <Input value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && send()} placeholder="Répondre..." className="rounded-full" data-testid="admin-chat-input" />
                <Button size="icon" onClick={send} className="rounded-full shrink-0" data-testid="admin-chat-send"><Send className="h-4 w-4" /></Button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

const C_STATUS = {
  en_cours: { l: "En cours", c: "status-pending" },
  boucle: { l: "Bouclé", c: "status-accepted" },
  resilie: { l: "Résilié", c: "status-rejected" },
};
const EMPTY_CONTRACT = { title: "", client: "", candidate_name: "", job_title: "", amount: "", start_date: "", end_date: "", status: "en_cours", notes: "" };

function Contracts() {
  const [list, setList] = useState([]);
  const [filter, setFilter] = useState("all");
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_CONTRACT);
  const [del, setDel] = useState(null);
  const load = useCallback(() => api.get(`/contracts?status=${filter}`).then(({ data }) => setList(data)).catch(() => {}), [filter]);
  useEffect(() => { load(); }, [load]);
  const openNew = () => { setEditing(null); setForm(EMPTY_CONTRACT); setOpen(true); };
  const openEdit = (c) => { setEditing(c); setForm({ ...EMPTY_CONTRACT, ...c }); setOpen(true); };
  const save = async () => {
    try {
      if (editing) await api.put(`/contracts/${editing.id}`, form);
      else await api.post(`/contracts`, form);
      toast.success(editing ? "Contrat mis à jour" : "Contrat créé");
      setOpen(false); load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };
  const remove = async () => { await api.delete(`/contracts/${del.id}`); toast.success("Contrat supprimé"); setDel(null); load(); };

  return (
    <div>
      <div className="flex items-center justify-between mb-6 gap-3 flex-wrap">
        <h1 className="font-display text-3xl font-semibold">Contrats</h1>
        <div className="flex items-center gap-2">
          <Button asChild variant="outline" className="rounded-full" data-testid="export-contracts-btn">
            <a href={`${API}/export/contracts?auth=${encodeURIComponent(localStorage.getItem("token") || "")}`}><Download className="h-4 w-4 mr-2" /> Export CSV</a>
          </Button>
          <Select value={filter} onValueChange={setFilter}>
            <SelectTrigger className="w-40 rounded-full" data-testid="contract-filter"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Tous</SelectItem>
              <SelectItem value="en_cours">En cours</SelectItem>
              <SelectItem value="boucle">Bouclés</SelectItem>
              <SelectItem value="resilie">Résiliés</SelectItem>
            </SelectContent>
          </Select>
          <Button onClick={openNew} className="rounded-full" data-testid="new-contract-btn"><Plus className="h-4 w-4 mr-2" /> Nouveau</Button>
        </div>
      </div>

      {list.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-16 text-center text-muted-foreground">Aucun contrat.</div>
      ) : (
        <div className="rounded-2xl border border-border bg-card overflow-hidden">
          <Table>
            <TableHeader><TableRow><TableHead>Intitulé</TableHead><TableHead>Client</TableHead><TableHead>Candidat</TableHead><TableHead>Montant</TableHead><TableHead>Statut</TableHead><TableHead className="text-right">Actions</TableHead></TableRow></TableHeader>
            <TableBody>
              {list.map((c) => (
                <TableRow key={c.id} data-testid={`contract-row-${c.id}`}>
                  <TableCell className="font-medium">{c.title}</TableCell>
                  <TableCell className="text-muted-foreground">{c.client}</TableCell>
                  <TableCell className="text-muted-foreground">{c.candidate_name}</TableCell>
                  <TableCell>{c.amount}</TableCell>
                  <TableCell><span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${(C_STATUS[c.status] || C_STATUS.en_cours).c}`}>{(C_STATUS[c.status] || C_STATUS.en_cours).l}</span></TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="icon" onClick={() => openEdit(c)} data-testid={`edit-contract-${c.id}`}><Pencil className="h-4 w-4" /></Button>
                    <Button variant="ghost" size="icon" onClick={() => setDel(c)} data-testid={`delete-contract-${c.id}`}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader><DialogTitle>{editing ? "Modifier le contrat" : "Nouveau contrat"}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>Intitulé</Label><Input data-testid="contract-title-input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="mt-1" /></div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Client / Chef de projet</Label><Input value={form.client} onChange={(e) => setForm({ ...form, client: e.target.value })} className="mt-1" /></div>
              <div><Label>Candidat</Label><Input value={form.candidate_name} onChange={(e) => setForm({ ...form, candidate_name: e.target.value })} className="mt-1" /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Offre liée</Label><Input value={form.job_title} onChange={(e) => setForm({ ...form, job_title: e.target.value })} className="mt-1" /></div>
              <div><Label>Montant</Label><Input value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} className="mt-1" /></div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Début</Label><Input type="date" value={form.start_date} onChange={(e) => setForm({ ...form, start_date: e.target.value })} className="mt-1" /></div>
              <div><Label>Fin</Label><Input type="date" value={form.end_date} onChange={(e) => setForm({ ...form, end_date: e.target.value })} className="mt-1" /></div>
            </div>
            <div>
              <Label>Statut</Label>
              <Select value={form.status} onValueChange={(v) => setForm({ ...form, status: v })}>
                <SelectTrigger className="mt-1" data-testid="contract-status-select"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="en_cours">En cours</SelectItem>
                  <SelectItem value="boucle">Bouclé</SelectItem>
                  <SelectItem value="resilie">Résilié</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div><Label>Notes</Label><Textarea rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} className="mt-1" /></div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)} className="rounded-full">Annuler</Button>
            <Button onClick={save} disabled={!form.title} className="rounded-full" data-testid="save-contract-btn">Enregistrer</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!del} onOpenChange={() => setDel(null)}>
        <AlertDialogContent>
          <AlertDialogHeader><AlertDialogTitle>Supprimer ce contrat ?</AlertDialogTitle><AlertDialogDescription>Action irréversible.</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter><AlertDialogCancel>Annuler</AlertDialogCancel><AlertDialogAction onClick={remove} data-testid="confirm-delete-contract">Supprimer</AlertDialogAction></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

const EMPTY_ITW = { title: "", candidate_name: "", date: "", time: "", location: "", notes: "", status: "scheduled" };

function Interviews() {
  const [list, setList] = useState([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_ITW);
  const [del, setDel] = useState(null);
  const [call, setCall] = useState(null);
  const load = useCallback(() => api.get(`/interviews`).then(({ data }) => setList(data)).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);
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

  const groups = list.reduce((acc, i) => { (acc[i.date] = acc[i.date] || []).push(i); return acc; }, {});
  const dates = Object.keys(groups).sort();
  const fmtDate = (d) => { try { return new Date(d + "T00:00:00").toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long", year: "numeric" }); } catch { return d; } };

  return (
    <div>
      {call && <VideoCall room={call.room} audioOnly={call.audioOnly} title={`Entretien`} onClose={() => setCall(null)} />}
      <div className="flex items-center justify-between mb-6 gap-3 flex-wrap">
        <div>
          <h1 className="font-display text-3xl font-semibold">Agenda des entretiens</h1>
          <p className="text-muted-foreground text-sm">{list.length} entretien{list.length > 1 ? "s" : ""} planifié{list.length > 1 ? "s" : ""}</p>
        </div>
        <Button onClick={openNew} className="rounded-full" data-testid="new-interview-btn"><Plus className="h-4 w-4 mr-2" /> Planifier</Button>
      </div>

      {dates.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-16 text-center text-muted-foreground">
          <CalendarDays className="h-12 w-12 text-muted-foreground/40 mx-auto mb-4" />
          Aucun entretien planifié.
        </div>
      ) : (
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
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle>{editing ? "Modifier l'entretien" : "Nouvel entretien"}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            <div><Label>Intitulé</Label><Input data-testid="interview-title-input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} className="mt-1" placeholder="Ex : Entretien technique" /></div>
            <div><Label>Candidat</Label><Input value={form.candidate_name} onChange={(e) => setForm({ ...form, candidate_name: e.target.value })} className="mt-1" /></div>
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

function ThemeSection() {
  const { theme, saveTheme, previewTheme } = useTheme();
  const [custom, setCustom] = useState("#1e40af");

  const applyPreset = async (p) => {
    await saveTheme(p.primary, p.fg, p.name);
    toast.success(`Thème "${p.name}" appliqué`);
  };
  const applyCustom = async () => {
    const hsl = hexToHsl(custom);
    await saveTheme(hsl, "0 0% 100%", "Personnalisé");
    toast.success("Couleur personnalisée appliquée");
  };

  return (
    <div>
      <h1 className="font-display text-3xl font-semibold mb-2">Apparence</h1>
      <p className="text-muted-foreground mb-6">Changez la couleur principale de toute l'application. Thème actuel : <strong>{theme.name}</strong></p>

      <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-8">
        {PRESETS.map((p) => (
          <button key={p.name} onClick={() => applyPreset(p)} onMouseEnter={() => previewTheme(p.primary, p.fg)} onMouseLeave={() => previewTheme(theme.primary, theme.primary_foreground)} data-testid={`theme-${p.name}`} className="rounded-2xl border border-border bg-card p-5 text-left hover:-translate-y-1 hover:shadow-lg transition-transform">
            <div className="h-12 w-12 rounded-xl mb-3" style={{ background: `hsl(${p.primary})` }} />
            <p className="font-medium text-sm">{p.name}</p>
          </button>
        ))}
      </div>

      <div className="rounded-2xl border border-border bg-card p-6 max-w-md">
        <p className="font-medium mb-3">Couleur personnalisée</p>
        <div className="flex items-center gap-3">
          <input type="color" value={custom} onChange={(e) => setCustom(e.target.value)} className="h-11 w-16 rounded-lg border border-border cursor-pointer" data-testid="custom-color-input" />
          <Input value={custom} onChange={(e) => setCustom(e.target.value)} className="flex-1" />
          <Button onClick={applyCustom} className="rounded-full" data-testid="apply-custom-color-btn">Appliquer</Button>
        </div>
      </div>
    </div>
  );
}
