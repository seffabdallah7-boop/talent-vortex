import { useEffect, useState, useCallback, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
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
import { Switch } from "@/components/ui/switch";
import {
  AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription,
  AlertDialogFooter, AlertDialogCancel, AlertDialogAction,
} from "@/components/ui/alert-dialog";
import {
  LayoutGrid, Briefcase, Users, FileText, MessageSquare, Palette, Plus, Trash2, Pencil,
  LogOut, Volume2, Send, Loader2, Building2, CheckCircle2, Sun, Moon, Menu, Film, PhoneCall,
  CalendarDays, ScrollText, Download, Star, Video, Phone, Sparkles, ChevronLeft, ChevronRight, Link2, Check, Paperclip, Mic, Square,
} from "lucide-react";
import { toast } from "sonner";
import VideoCall from "@/components/VideoCall";
import { Avatar } from "@/components/Avatar";
import CandidateProfileDialog from "@/components/CandidateProfileDialog";
import ChatMessageBubble from "@/components/ChatMessageBubble";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { NotificationBell } from "@/components/Navbar";
import { LanguageSwitcher } from "@/components/LanguageSwitcher";

const NAV = [
  { key: "overview", label: "Tableau de bord", Icon: LayoutGrid },
  { key: "jobs", label: "Offres d'emploi", Icon: Briefcase },
  { key: "applications", label: "Candidatures", Icon: FileText },
  { key: "contracts", label: "Contrats", Icon: ScrollText },
  { key: "interviews", label: "Agenda entretiens", Icon: CalendarDays },
  { key: "candidates", label: "Utilisateurs", Icon: Users },
  { key: "messages", label: "Messages", Icon: MessageSquare },
  { key: "meeting", label: "Salle de réunion", Icon: PhoneCall },
  { key: "recordings", label: "Enregistrements", Icon: Film },
  { key: "suggestions", label: "Suggestions IA", Icon: Sparkles },
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

function NavButtons({ section, onSelect }) {
  return NAV.map((n) => (
    <button
      key={n.key}
      onClick={() => onSelect(n.key)}
      data-testid={`nav-${n.key}`}
      className={`w-full flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${section === n.key ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-secondary"}`}
    >
      <n.Icon className="h-4.5 w-4.5" /> {n.label}
    </button>
  ));
}

export default function AdminDashboard() {
  const { user, logout } = useAuth();
  const { dark, toggle } = useDarkMode();
  const navigate = useNavigate();
  const [section, setSection] = useState("overview");
  const [jobFilter, setJobFilter] = useState(null);
  const [profileId, setProfileId] = useState(null);
  const [mobileNav, setMobileNav] = useState(false);
  const [appStatus, setAppStatus] = useState("all");
  const [contractStatus, setContractStatus] = useState("all");
  const [activeCall, setActiveCall] = useState(null);
  const [chatFocus, setChatFocus] = useState(null);
  const [initialSuggestionJob, setInitialSuggestionJob] = useState(null);
  const [searchParams] = useSearchParams();

  useEffect(() => {
    const s = searchParams.get("section");
    const candidate = searchParams.get("candidate");
    const name = searchParams.get("name");
    const profile = searchParams.get("profile");
    const job = searchParams.get("job");
    if (s) setSection(s);
    if (candidate) setChatFocus({ candidate_id: candidate, candidate_name: name || "" });
    if (profile) setProfileId(profile);
    if (job) setInitialSuggestionJob(job);
  }, [searchParams]);

  const callCandidate = async (candidate_id, candidate_name, mode) => {
    try {
      const { data } = await api.post("/calls", { callee_id: candidate_id, mode: mode === "audio" ? "audio" : "video" });
      setActiveCall({ room: data.room, audioOnly: mode === "audio", recordCtx: { candidate_id, candidate_name, title: `Entretien — ${candidate_name || ""}`.trim() } });
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail) || "Impossible de démarrer l'appel"); }
  };

  const selectSection = (key) => {
    setSection(key);
    if (key === "applications") { setJobFilter(null); setAppStatus("all"); }
    setMobileNav(false);
  };

  const goto = (key, opts = {}) => {
    setAppStatus(opts.appStatus ?? "all");
    if (opts.contractStatus !== undefined) setContractStatus(opts.contractStatus);
    if (key === "applications") setJobFilter(null);
    setSection(key);
  };

  useEffect(() => {
    const ping = () => api.post("/presence/ping").catch(() => {});
    ping();
    const t = setInterval(ping, 30000);
    return () => clearInterval(t);
  }, []);

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
          <NavButtons section={section} onSelect={selectSection} />
        </nav>
        <div className="p-3 border-t border-border space-y-2">
          <p className="text-xs text-muted-foreground truncate px-1">{user?.email}</p>
          <Button variant="outline" className="w-full rounded-lg" onClick={() => { logout(); navigate("/"); }} data-testid="admin-logout-btn">
            <LogOut className="h-4 w-4 mr-2" /> Déconnexion
          </Button>
        </div>
      </aside>

      <main className="flex-1 overflow-y-auto">
        <div className="hidden md:flex items-center justify-end gap-2 px-8 h-16 border-b border-border sticky top-0 bg-background/80 backdrop-blur-md z-20" data-testid="admin-header">
          <LanguageSwitcher />
          <NotificationBell />
          <button
            onClick={toggle}
            data-testid="admin-dark-toggle"
            aria-label="Basculer le thème"
            className="h-9 w-9 rounded-full border border-border flex items-center justify-center hover:bg-secondary transition-colors"
          >
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
        </div>
        <div className="md:hidden flex items-center gap-3 p-3 border-b border-border">
          <Sheet open={mobileNav} onOpenChange={setMobileNav}>
            <SheetTrigger asChild>
              <button className="h-10 w-10 rounded-lg border border-border flex items-center justify-center hover:bg-secondary transition-colors" data-testid="mobile-menu-btn" aria-label="Menu">
                <Menu className="h-5 w-5" />
              </button>
            </SheetTrigger>
            <SheetContent side="left" className="p-0 w-72 flex flex-col">
              <SheetHeader className="p-4 border-b border-border text-left">
                <SheetTitle className="flex items-center gap-2">
                  <div className="h-8 w-8 rounded-lg bg-primary flex items-center justify-center"><Briefcase className="h-4 w-4 text-primary-foreground" /></div>
                  Talent Vortex
                </SheetTitle>
              </SheetHeader>
              <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
                <NavButtons section={section} onSelect={selectSection} />
              </nav>
              <div className="p-3 border-t border-border">
                <Button variant="outline" className="w-full rounded-lg" onClick={() => { logout(); navigate("/"); }} data-testid="mobile-logout-btn">
                  <LogOut className="h-4 w-4 mr-2" /> Déconnexion
                </Button>
              </div>
            </SheetContent>
          </Sheet>
          <span className="font-display text-lg font-semibold flex items-center gap-2">
            <div className="h-7 w-7 rounded-md bg-primary flex items-center justify-center"><Briefcase className="h-4 w-4 text-primary-foreground" /></div>
            Talent Vortex
          </span>
          <div className="ml-auto flex items-center gap-2"><LanguageSwitcher /><NotificationBell /></div>
        </div>
        <div className="p-6 md:p-8 max-w-6xl">
          {section === "overview" && <Overview onNavigate={goto} />}
          {section === "jobs" && <Jobs onViewApplications={(job) => { setJobFilter(job); setSection("applications"); }} />}
          {section === "applications" && <Applications jobFilter={jobFilter} initialStatus={appStatus} onClearJobFilter={() => setJobFilter(null)} onOpenProfile={setProfileId} />}
          {section === "contracts" && <Contracts initialFilter={contractStatus} />}
          {section === "interviews" && <Interviews />}
          {section === "candidates" && <Candidates onOpenProfile={setProfileId} />}
          {section === "messages" && <Messages onOpenProfile={setProfileId} focus={chatFocus} />}
          {section === "meeting" && <Meetings />}
          {section === "recordings" && <Recordings />}
          {section === "suggestions" && <Suggestions onOpenProfile={setProfileId} initialJob={initialSuggestionJob} />}
          {section === "theme" && <ThemeSection />}
        </div>
      </main>
      <CandidateProfileDialog
        userId={profileId}
        open={!!profileId}
        onClose={() => setProfileId(null)}
        onChat={(u) => { setProfileId(null); setChatFocus({ candidate_id: u.user_id, candidate_name: u.name }); setSection("messages"); }}
        onCall={(u, mode) => { setProfileId(null); callCandidate(u.user_id, u.name, mode); }}
      />
      {activeCall && <VideoCall room={activeCall.room} audioOnly={activeCall.audioOnly} title={activeCall.recordCtx?.title} recordCtx={activeCall.recordCtx} onClose={() => setActiveCall(null)} />}
    </div>
  );
}

function Overview({ onNavigate }) {
  const [stats, setStats] = useState(null);
  useEffect(() => { api.get("/admin/stats").then(({ data }) => setStats(data)).catch(() => {}); }, []);
  if (!stats) return <Loader2 className="h-6 w-6 animate-spin text-primary" />;
  const cards = [
    { label: "Offres actives", value: stats.active_jobs, Icon: Briefcase, target: ["jobs"] },
    { label: "Candidats", value: stats.candidates, Icon: Users, target: ["candidates"] },
    { label: "Candidatures", value: stats.applications, Icon: FileText, target: ["applications", { appStatus: "all" }] },
    { label: "En attente", value: stats.pending, Icon: CheckCircle2, target: ["applications", { appStatus: "pending" }] },
    { label: "Contrats actifs", value: stats.contracts_active, Icon: ScrollText, target: ["contracts", { contractStatus: "en_cours" }] },
    { label: "Entretiens à venir", value: stats.upcoming_interviews, Icon: CalendarDays, target: ["interviews"] },
  ];
  return (
    <div>
      <h1 className="font-display text-3xl font-semibold mb-6">Tableau de bord</h1>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        {cards.map((c) => (
          <button
            key={c.label}
            onClick={() => onNavigate(...c.target)}
            data-testid={`stat-${c.label}`}
            className="text-left rounded-2xl border border-border bg-card p-5 hover:border-primary hover:-translate-y-0.5 transition-all"
          >
            <c.Icon className="h-5 w-5 text-primary mb-3" />
            <p className="font-display text-3xl font-semibold">{c.value}</p>
            <p className="text-sm text-muted-foreground">{c.label}</p>
          </button>
        ))}
      </div>
      <div className="grid grid-cols-3 gap-4">
        <button onClick={() => onNavigate("applications", { appStatus: "pending" })} data-testid="stat-card-pending" className="text-left rounded-2xl border status-pending p-5 hover:opacity-90 transition-opacity"><p className="font-display text-2xl font-semibold">{stats.pending}</p><p className="text-sm">En attente</p></button>
        <button onClick={() => onNavigate("applications", { appStatus: "accepted" })} data-testid="stat-card-accepted" className="text-left rounded-2xl border status-accepted p-5 hover:opacity-90 transition-opacity"><p className="font-display text-2xl font-semibold">{stats.accepted}</p><p className="text-sm">Acceptées</p></button>
        <button onClick={() => onNavigate("applications", { appStatus: "rejected" })} data-testid="stat-card-rejected" className="text-left rounded-2xl border status-rejected p-5 hover:opacity-90 transition-opacity"><p className="font-display text-2xl font-semibold">{stats.rejected}</p><p className="text-sm">Refusées</p></button>
      </div>
    </div>
  );
}

const EMPTY_JOB = { title: "", company: "", location: "", type: "Temps plein", category: "General", description: "", requirements: "", salary: "" };

function Jobs({ onViewApplications }) {
  const navigate = useNavigate();
  const [jobs, setJobs] = useState([]);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_JOB);
  const [saving, setSaving] = useState(false);
  const [del, setDel] = useState(null);
  const [aiBrief, setAiBrief] = useState("");
  const [aiLoading, setAiLoading] = useState(false);

  const load = useCallback(() => api.get("/jobs/all").then(({ data }) => setJobs(data)).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);

  const openNew = () => { setEditing(null); setForm(EMPTY_JOB); setAiBrief(""); setOpen(true); };
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

  const toggleActive = async (j) => {
    try {
      await api.put(`/jobs/${j.id}/active`, { is_active: !j.is_active });
      toast.success(j.is_active ? "Offre masquée" : "Offre visible");
      load();
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
  };

  const generateAi = async () => {
    setAiLoading(true);
    try {
      const { data } = await api.post("/jobs/ai-draft", { brief: aiBrief });
      setForm((f) => ({ ...EMPTY_JOB, ...f, ...data }));
      toast.success("Offre pré-remplie par l'IA. Vérifiez et ajustez avant de publier.");
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setAiLoading(false); }
  };

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
            <TableHeader><TableRow><TableHead>Poste</TableHead><TableHead>Lieu</TableHead><TableHead>Candidatures</TableHead><TableHead>Visible</TableHead><TableHead className="text-right">Actions</TableHead></TableRow></TableHeader>
            <TableBody>
              {jobs.map((j) => (
                <TableRow key={j.id} data-testid={`job-row-${j.id}`}>
                  <TableCell>
                    <button onClick={() => navigate(`/jobs/${j.id}`)} className="text-left hover:text-primary transition-colors" data-testid={`open-job-${j.id}`}>
                      <div className="font-medium">{j.title}</div>
                      <div className="text-xs text-muted-foreground">{j.company}</div>
                    </button>
                  </TableCell>
                  <TableCell>{j.location}</TableCell>
                  <TableCell>
                    <button onClick={() => onViewApplications({ id: j.id, title: j.title })} data-testid={`view-job-apps-${j.id}`} className="inline-flex items-center gap-1.5 hover:opacity-80">
                      <span className="rounded-full bg-secondary px-2.5 py-0.5 text-xs font-medium">{j.applicants || 0}</span>
                      {j.pending > 0 && <span className="rounded-full bg-primary text-primary-foreground px-2 py-0.5 text-xs font-semibold" data-testid={`job-pending-${j.id}`}>{j.pending} nouv.</span>}
                    </button>
                  </TableCell>
                  <TableCell><Switch checked={!!j.is_active} onCheckedChange={() => toggleActive(j)} data-testid={`toggle-job-${j.id}`} /></TableCell>
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
            {!editing && (
              <div className="rounded-xl border border-primary/30 bg-primary/5 p-3 space-y-2" data-testid="ai-job-panel">
                <Label className="flex items-center gap-1.5 text-primary"><Sparkles className="h-4 w-4" /> Générer avec l'IA</Label>
                <Textarea data-testid="ai-brief-input" rows={3} value={aiBrief} onChange={(e) => setAiBrief(e.target.value)} placeholder="Collez une fiche de poste ou décrivez le poste en quelques mots — l'IA pré-remplit le formulaire." className="bg-card" />
                <Button type="button" size="sm" onClick={generateAi} disabled={aiLoading || !aiBrief.trim()} className="rounded-full" data-testid="ai-generate-btn">
                  {aiLoading ? <><Loader2 className="h-4 w-4 animate-spin mr-2" /> Génération...</> : <><Sparkles className="h-4 w-4 mr-2" /> Pré-remplir avec l'IA</>}
                </Button>
              </div>
            )}
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

function Applications({ jobFilter, onClearJobFilter, onOpenProfile, initialStatus }) {
  const [apps, setApps] = useState([]);
  const [filter, setFilter] = useState(initialStatus || "all");
  const [detail, setDetail] = useState(null);
  const [del, setDel] = useState(null);
  const [note, setNote] = useState("");
  const [rating, setRating] = useState(0);
  const [search, setSearch] = useState("");
  const [jobs, setJobs] = useState([]);
  const [jobSel, setJobSel] = useState("all");

  useEffect(() => { setFilter(initialStatus || "all"); }, [initialStatus]);
  useEffect(() => { api.get("/jobs/all").then(({ data }) => setJobs(data)).catch(() => {}); }, []);

  const load = useCallback(() => {
    const params = new URLSearchParams();
    params.set("status", filter);
    const jid = jobFilter?.id || (jobSel !== "all" ? jobSel : null);
    if (jid) params.set("job_id", jid);
    return api.get(`/applications?${params.toString()}`).then(({ data }) => setApps(data)).catch(() => {});
  }, [filter, jobFilter, jobSel]);
  useEffect(() => { load(); }, [load]);

  const [schedule, setSchedule] = useState(null);
  const [examApp, setExamApp] = useState(null);
  const [itwForm, setItwForm] = useState({ title: "", date: "", time: "", location: "", notes: "" });
  const [scheduling, setScheduling] = useState(false);

  const accept = async () => {
    await setStatus(detail.id, "accepted");
    const app = detail;
    setDetail(null);
    setItwForm({ title: `Entretien — ${app.job_title}`, date: "", time: "", location: "", notes: "" });
    setSchedule({ candidate_id: app.candidate_id, candidate_name: app.candidate_name, application_id: app.id });
  };
  const saveSchedule = async () => {
    setScheduling(true);
    try {
      await api.post("/interviews", {
        title: itwForm.title, candidate_id: schedule.candidate_id, candidate_name: schedule.candidate_name,
        application_id: schedule.application_id, date: itwForm.date, time: itwForm.time,
        location: itwForm.location, notes: itwForm.notes, status: "scheduled",
      });
      toast.success("Entretien planifié — le candidat a été notifié.");
      setSchedule(null);
    } catch (e) { toast.error(formatApiError(e.response?.data?.detail)); }
    finally { setScheduling(false); }
  };

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
        <div className="flex items-center gap-2 flex-wrap">
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Rechercher un candidat, poste..." className="w-56 rounded-full" data-testid="app-search-input" />
          {!jobFilter && (
            <Select value={jobSel} onValueChange={setJobSel}>
              <SelectTrigger className="w-52 rounded-full" data-testid="app-job-filter"><SelectValue placeholder="Toutes les offres" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Toutes les offres</SelectItem>
                {jobs.map((j) => <SelectItem key={j.id} value={j.id}>{j.title}</SelectItem>)}
              </SelectContent>
            </Select>
          )}
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

      {jobFilter && (
        <div className="mb-4 flex items-center gap-2" data-testid="job-filter-chip">
          <span className="rounded-full bg-primary/10 text-primary px-3 py-1 text-sm font-medium">Candidatures pour : {jobFilter.title}</span>
          <Button variant="ghost" size="sm" className="rounded-full" onClick={onClearJobFilter} data-testid="clear-job-filter">Voir toutes</Button>
        </div>
      )}

      {apps.filter((a) => { const q = search.trim().toLowerCase(); return !q || (a.candidate_name || "").toLowerCase().includes(q) || (a.candidate_email || "").toLowerCase().includes(q) || (a.job_title || "").toLowerCase().includes(q); }).length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-16 text-center text-muted-foreground">Aucune candidature.</div>
      ) : (
        <div className="rounded-2xl border border-border bg-card overflow-hidden">
          <Table>
            <TableHeader><TableRow><TableHead>Candidat</TableHead><TableHead>Poste</TableHead><TableHead>Statut</TableHead><TableHead className="text-right">Action</TableHead></TableRow></TableHeader>
            <TableBody>
              {apps.filter((a) => { const q = search.trim().toLowerCase(); return !q || (a.candidate_name || "").toLowerCase().includes(q) || (a.candidate_email || "").toLowerCase().includes(q) || (a.job_title || "").toLowerCase().includes(q); }).map((a) => (
                <TableRow key={a.id} className="cursor-pointer" onClick={() => setDetail(a)} data-testid={`app-row-${a.id}`}>
                  <TableCell>
                    <div className="flex items-center gap-3">
                      <Avatar
                        name={a.candidate_name}
                        src={a.candidate_picture}
                        size={36}
                        onClick={(e) => { e.stopPropagation(); onOpenProfile(a.candidate_id); }}
                        testId={`app-avatar-${a.id}`}
                      />
                      <div>
                        <div className="font-medium">{a.candidate_name}</div>
                        <div className="text-xs text-muted-foreground">{a.candidate_email}</div>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell>{a.job_title}</TableCell>
                  <TableCell><StatusBadge status={a.status} /></TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button variant="outline" size="sm" className="rounded-full">Examiner</Button>
                      <Button variant="ghost" size="icon" onClick={(e) => { e.stopPropagation(); setDel(a); }} data-testid={`delete-app-row-${a.id}`}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                    </div>
                  </TableCell>
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
              <DialogHeader>
                <DialogTitle className="flex items-center gap-3">
                  <Avatar name={detail.candidate_name} src={detail.candidate_picture} size={40} />
                  {detail.candidate_name}
                </DialogTitle>
              </DialogHeader>
              <div className="space-y-4">
                <div className="flex items-center gap-2 flex-wrap">
                  <StatusBadge status={detail.status} />
                  <span className="text-sm text-muted-foreground">• {detail.job_title}</span>
                  <Button variant="outline" size="sm" className="rounded-full ml-auto" onClick={() => onOpenProfile(detail.candidate_id)} data-testid="view-full-profile-btn">Voir le profil complet</Button>
                </div>
                {detail.screening?.completed && (
                  <Button variant="outline" size="sm" className="rounded-full w-fit" onClick={() => setExamApp(detail)} data-testid="view-exam-btn"><Sparkles className="h-4 w-4 mr-2" /> Voir l'examen IA</Button>
                )}
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
                    <Button size="sm" onClick={accept} className="rounded-full status-accepted border-0" data-testid="accept-btn">Accepter</Button>
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

      <Dialog open={!!examApp} onOpenChange={(v) => !v && setExamApp(null)}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          {examApp && (
            <>
              <DialogHeader><DialogTitle className="flex items-center gap-2"><Sparkles className="h-5 w-5 text-primary" /> Examen de pré-qualification (confidentiel)</DialogTitle></DialogHeader>
              <div className="space-y-4">
                <div className="rounded-xl bg-primary/5 border border-primary/20 p-4">
                  <div className="flex items-center justify-between mb-1">
                    <p className="text-xs font-semibold text-primary flex items-center gap-1.5"><Sparkles className="h-3.5 w-3.5" /> Avis de l'IA</p>
                    {typeof examApp.screening?.ai_score === "number" && <span className="text-sm font-bold text-primary" data-testid="exam-score">{examApp.screening.ai_score}/100</span>}
                  </div>
                  {examApp.screening?.ai_verdict && <p className="text-sm font-semibold mb-1" data-testid="exam-verdict">Verdict : {examApp.screening.ai_verdict}</p>}
                  <p className="text-sm whitespace-pre-wrap" data-testid="exam-analysis">{examApp.screening?.ai_assessment || "Analyse indisponible."}</p>
                </div>
                <div className="space-y-3">
                  {(examApp.screening?.questions || []).map((q, i) => (
                    <div key={i} className="rounded-lg border border-border p-3" data-testid={`exam-qa-${i}`}>
                      <p className="text-sm font-medium">{i + 1}. {q}</p>
                      <p className="text-sm text-muted-foreground mt-1">{examApp.screening?.answers?.[i] || "—"}</p>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={!!schedule} onOpenChange={(v) => !v && setSchedule(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Planifier l'entretien</DialogTitle></DialogHeader>
          {schedule && (
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">Candidat accepté : <b>{schedule.candidate_name}</b>. Fixez la date de l'entretien — il apparaîtra dans son espace et il sera notifié.</p>
              <div><Label>Intitulé</Label><Input data-testid="schedule-title-input" value={itwForm.title} onChange={(e) => setItwForm({ ...itwForm, title: e.target.value })} className="mt-1" /></div>
              <div className="grid grid-cols-2 gap-3">
                <div><Label>Date</Label><Input type="date" data-testid="schedule-date-input" value={itwForm.date} onChange={(e) => setItwForm({ ...itwForm, date: e.target.value })} className="mt-1" /></div>
                <div><Label>Heure</Label><Input type="time" data-testid="schedule-time-input" value={itwForm.time} onChange={(e) => setItwForm({ ...itwForm, time: e.target.value })} className="mt-1" /></div>
              </div>
              <div><Label>Lieu / Lien visio</Label><Input value={itwForm.location} onChange={(e) => setItwForm({ ...itwForm, location: e.target.value })} className="mt-1" placeholder="Visio (par défaut Jitsi)" /></div>
              <div><Label>Notes</Label><Textarea rows={2} value={itwForm.notes} onChange={(e) => setItwForm({ ...itwForm, notes: e.target.value })} className="mt-1" /></div>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" className="rounded-full" onClick={() => setSchedule(null)}>Plus tard</Button>
            <Button className="rounded-full" onClick={saveSchedule} disabled={scheduling || !itwForm.title || !itwForm.date || !itwForm.time} data-testid="save-schedule-btn">
              {scheduling ? <Loader2 className="h-4 w-4 animate-spin" /> : "Planifier"}
            </Button>
          </DialogFooter>
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

function Candidates({ onOpenProfile }) {
  const { user: me } = useAuth();
  const [list, setList] = useState([]);
  const [del, setDel] = useState(null);
  const [q, setQ] = useState("");
  const [minRating, setMinRating] = useState("all");
  const [nats, setNats] = useState([]);
  const load = useCallback(() => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (minRating !== "all") params.set("min_rating", minRating);
    return api.get(`/users?${params.toString()}`).then(({ data }) => setList(data)).catch(() => {});
  }, [q, minRating]);
  useEffect(() => { const t = setTimeout(load, 250); return () => clearTimeout(t); }, [load]);
  useEffect(() => { api.get("/admin/nationalities").then(({ data }) => setNats(data)).catch(() => {}); }, []);
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
      <div className="flex items-start justify-between gap-3 mb-6 flex-wrap">
        <div>
          <h1 className="font-display text-3xl font-semibold mb-2">Utilisateurs & rôles</h1>
          <p className="text-muted-foreground">Recherchez par nom, poste, domaine ou nationalité ; gérez les rôles.</p>
        </div>
        <div className="flex items-center gap-2 w-full sm:w-auto">
          <div className="flex-1 sm:w-72">
            <Input data-testid="candidate-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher (poste, domaine, nationalité...)" className="rounded-full" />
          </div>
          <Select value={minRating} onValueChange={setMinRating}>
            <SelectTrigger className="w-44 rounded-full shrink-0" data-testid="rating-filter"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Toute appréciation</SelectItem>
              <SelectItem value="5">5 ★</SelectItem>
              <SelectItem value="4">4 ★ et +</SelectItem>
              <SelectItem value="3">3 ★ et +</SelectItem>
              <SelectItem value="2">2 ★ et +</SelectItem>
              <SelectItem value="1">1 ★ et +</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>
      {nats.length > 0 && (
        <div className="rounded-2xl border border-border bg-card p-4 mb-6" data-testid="nationalities-panel">
          <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wide mb-3">Répartition par nationalité</p>
          <div className="flex flex-wrap gap-2">
            {nats.map((n) => (
              <span key={n.nationality} data-testid={`nat-${n.nationality}`} className="inline-flex items-center gap-1.5 rounded-full bg-secondary px-3 py-1 text-sm">
                {n.nationality}
                <span className="rounded-full bg-primary/15 text-primary px-1.5 text-xs font-bold">{n.count}</span>
              </span>
            ))}
          </div>
        </div>
      )}
      {list.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-16 text-center text-muted-foreground">Aucun utilisateur.</div>
      ) : (
        <div className="rounded-2xl border border-border bg-card overflow-hidden">
          <Table>
            <TableHeader><TableRow><TableHead>Nom</TableHead><TableHead>Email</TableHead><TableHead>Nationalité</TableHead><TableHead>Poste</TableHead><TableHead>Appréciation</TableHead><TableHead>Rôle</TableHead><TableHead>Cand.</TableHead><TableHead className="text-right">Actions</TableHead></TableRow></TableHeader>
            <TableBody>
              {list.map((u) => {
                const isSelf = me && u.user_id === me.user_id;
                return (
                  <TableRow key={u.user_id} data-testid={`candidate-row-${u.user_id}`}>
                    <TableCell className="font-medium">
                      <button className="flex items-center gap-3 hover:opacity-80 text-left" onClick={() => onOpenProfile(u.user_id)} data-testid={`open-profile-${u.user_id}`}>
                        <Avatar name={u.name} src={u.picture} size={36} />
                        <span>{u.name} {isSelf && <span className="text-xs text-muted-foreground">(vous)</span>}</span>
                      </button>
                    </TableCell>
                    <TableCell className="text-muted-foreground">{u.email}</TableCell>
                    <TableCell className="text-muted-foreground text-sm">{u.nationality || "—"}</TableCell>
                    <TableCell className="text-muted-foreground text-sm">{u.current_position || "—"}</TableCell>
                    <TableCell>
                      {u.rating ? (
                        <span className="inline-flex items-center gap-1 text-primary text-sm font-medium" data-testid={`rating-${u.user_id}`}>
                          <Star className="h-3.5 w-3.5 fill-primary" /> {u.rating}
                          <span className="text-muted-foreground text-xs">({u.rating_count})</span>
                        </span>
                      ) : <span className="text-muted-foreground text-sm">—</span>}
                    </TableCell>
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

const chatTime = (iso) => { try { return new Date(iso).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" }); } catch { return ""; } };
const relSeen = (iso) => {
  if (!iso) return "jamais";
  try {
    const s = Math.floor((Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 60) return "à l'instant";
    if (s < 3600) return `il y a ${Math.floor(s / 60)} min`;
    if (s < 86400) return `il y a ${Math.floor(s / 3600)} h`;
    return `le ${new Date(iso).toLocaleDateString("fr-FR")}`;
  } catch { return ""; }
};

function Messages({ onOpenProfile, focus }) {
  const [convs, setConvs] = useState([]);
  const [active, setActive] = useState(null);
  const [msgs, setMsgs] = useState([]);
  const [firstUnread, setFirstUnread] = useState(null);
  const [text, setText] = useState("");
  const [call, setCall] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [recording, setRecording] = useState(false);
  const fileInputRef = useRef(null);
  const recRef = useRef(null);
  const chunksRef = useRef([]);
  const unreadRef = useRef(null);
  const [candidates, setCandidates] = useState([]);
  const [otherTyping, setOtherTyping] = useState(false);
  const typingRef = useRef(0);
  const pingTyping = () => { const n = Date.now(); if (active && n - typingRef.current > 2500) { typingRef.current = n; api.post("/chat/typing", { candidate_id: active.candidate_id }).catch(() => {}); } };

  useEffect(() => { if (focus?.candidate_id) setActive(focus); }, [focus]);
  useEffect(() => { api.get("/candidates").then(({ data }) => setCandidates(data)).catch(() => {}); }, []);

  const loadConvs = useCallback(() => api.get("/chat/conversations").then(({ data }) => setConvs(data)).catch(() => {}), []);
  useEffect(() => {
    loadConvs();
    const int = setInterval(loadConvs, 5000);
    return () => clearInterval(int);
  }, [loadConvs]);

  useEffect(() => {
    if (!active) return;
    const load = () => api.get(`/chat/messages?candidate_id=${active.candidate_id}`).then(({ data }) => {
      if (Array.isArray(data)) { setMsgs(data); }
      else { setMsgs(data.messages || []); setFirstUnread(data.first_unread || null); setOtherTyping(!!data.other_typing); }
    }).catch(() => {});
    load();
    const int = setInterval(load, 4000);
    return () => clearInterval(int);
  }, [active]);

  useEffect(() => {
    if (firstUnread && unreadRef.current) setTimeout(() => unreadRef.current?.scrollIntoView({ block: "center", behavior: "smooth" }), 100);
  }, [firstUnread, msgs]);

  const send = async () => {
    if (!text.trim() || !active) return;
    const { data } = await api.post("/chat/messages", { text: text.trim(), candidate_id: active.candidate_id });
    setMsgs((m) => [...m, data]);
    setText("");
  };

  const reload = () => active && api.get(`/chat/messages?candidate_id=${active.candidate_id}`).then(({ data }) => { setMsgs(Array.isArray(data) ? data : (data.messages || [])); setFirstUnread(Array.isArray(data) ? null : (data.first_unread || null)); }).catch(() => {});

  const onPickFile = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file || !active) return;
    setUploading(true);
    try { const { data } = await sendChatAttachment({ file, candidateId: active.candidate_id, text: "" }); setMsgs((m) => [...m, data]); }
    catch { toast.error("Échec de l'envoi du fichier"); }
    finally { setUploading(false); }
  };

  const startRec = async () => {
    if (!active) return;
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      chunksRef.current = [];
      mr.ondataavailable = (e) => e.data.size && chunksRef.current.push(e.data);
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        setUploading(true);
        try { const { data } = await sendChatAttachment({ file: blob, filename: "vocal.webm", candidateId: active.candidate_id, text: "" }); setMsgs((m) => [...m, data]); }
        catch { toast.error("Échec de l'envoi du vocal"); }
        finally { setUploading(false); }
      };
      recRef.current = mr;
      mr.start();
      setRecording(true);
    } catch { toast.error("Micro inaccessible."); }
  };
  const stopRec = () => { if (recRef.current?.state !== "inactive") recRef.current.stop(); setRecording(false); };

  const editMsg = async (m, t) => { try { await api.put(`/chat/messages/${m.id}`, { text: t }); reload(); } catch { toast.error("Échec de la modification"); } };
  const deleteMsg = async (m) => { try { await api.delete(`/chat/messages/${m.id}`); reload(); } catch { toast.error("Échec de la suppression"); } };

  const toggleActive = async () => {
    if (!active) return;
    const na = !(convs.find((c) => c.candidate_id === active.candidate_id)?.active);
    try { await api.put(`/chat/conversations/${active.candidate_id}/active`, { active: na }); toast.success(na ? "Conversation activée — le candidat peut y accéder." : "Conversation désactivée."); loadConvs(); }
    catch { toast.error("Action impossible"); }
  };
  const startConv = async (candId) => {
    const c = candidates.find((x) => x.user_id === candId);
    if (!c) return;
    try { await api.put(`/chat/conversations/${candId}/active`, { active: true }); toast.success("Discussion activée"); loadConvs(); setActive({ candidate_id: candId, candidate_name: c.name, picture: c.picture }); }
    catch { toast.error("Impossible de démarrer la discussion"); }
  };

  const activeConv = active ? (convs.find((c) => c.candidate_id === active.candidate_id) || active) : null;

  return (
    <div>
      {call && <VideoCall room={call.room} audioOnly={call.audioOnly} onClose={() => setCall(null)} />}
      <h1 className="font-display text-3xl font-semibold mb-6">Messages</h1>
      <div className="grid md:grid-cols-3 gap-4 h-[560px]">
        <div className="rounded-2xl border border-border bg-card overflow-y-auto">
          <div className="p-2 border-b border-border">
            <Select value="" onValueChange={startConv}>
              <SelectTrigger className="w-full rounded-full" data-testid="new-conv-select"><SelectValue placeholder="+ Nouvelle discussion" /></SelectTrigger>
              <SelectContent>
                {candidates.map((c) => <SelectItem key={c.user_id} value={c.user_id}>{c.name} — {c.email}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          {convs.length === 0 ? <p className="p-6 text-sm text-muted-foreground">Aucune conversation.</p> : convs.map((c) => (
            <button key={c.candidate_id} onClick={() => setActive(c)} data-testid={`conv-${c.candidate_id}`} className={`w-full text-left p-4 border-b border-border hover:bg-secondary transition-colors ${active?.candidate_id === c.candidate_id ? "bg-secondary" : ""}`}>
              <div className="flex items-center gap-3">
                <div className="relative shrink-0">
                  <Avatar name={c.candidate_name} src={c.picture} size={40} />
                  <span className={`absolute -bottom-0.5 -right-0.5 h-3 w-3 rounded-full border-2 border-card ${c.online ? "bg-green-500" : "bg-muted-foreground/40"}`} data-testid={`conv-presence-${c.candidate_id}`} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-sm truncate">{c.candidate_name || "Candidat"}</span>
                    <span className="text-[10px] text-muted-foreground shrink-0" data-testid={`conv-time-${c.candidate_id}`}>{c.last_at ? chatTime(c.last_at) : ""}</span>
                  </div>
                  <div className="flex items-center justify-between gap-2 mt-0.5">
                    <p className="text-xs text-muted-foreground truncate">{c.last_text || (c.last_at ? "Pièce jointe" : "Discussion activée")}</p>
                    <div className="flex items-center gap-1 shrink-0">
                      {!c.active && <span className="text-[9px] rounded-full bg-muted px-1.5 py-0.5 text-muted-foreground" data-testid={`conv-inactive-${c.candidate_id}`}>inactive</span>}
                      {c.unread > 0 && <span className="h-5 min-w-5 px-1 rounded-full bg-primary text-primary-foreground text-xs flex items-center justify-center">{c.unread}</span>}
                    </div>
                  </div>
                </div>
              </div>
            </button>
          ))}
        </div>
        <div className="md:col-span-2 rounded-2xl border border-border bg-card flex flex-col">
          {!active ? (
            <div className="flex-1 flex items-center justify-center text-muted-foreground text-sm">Sélectionnez une conversation</div>
          ) : (
            <>
              <div className="p-4 border-b border-border flex items-center justify-between">
                <button className="flex items-center gap-3 hover:opacity-80 text-left" onClick={() => onOpenProfile(active.candidate_id)} data-testid="chat-open-profile">
                  <Avatar name={active.candidate_name} src={activeConv?.picture} size={40} />
                  <div>
                    <div className="font-medium">{active.candidate_name || "Candidat"}</div>
                    <div className="text-xs text-muted-foreground flex items-center gap-1.5" data-testid="active-presence">
                      <span className={`h-2 w-2 rounded-full ${activeConv?.online ? "bg-green-500" : "bg-muted-foreground/40"}`} />
                      {activeConv?.online ? "En ligne" : `Hors ligne · vu ${relSeen(activeConv?.last_seen)}`}
                    </div>
                  </div>
                </button>
                <div className="flex gap-2">
                  <Button size="sm" variant={activeConv?.active ? "default" : "outline"} className="rounded-full" onClick={toggleActive} data-testid="toggle-conv-active">{activeConv?.active ? "Désactiver" : "Activer"}</Button>
                  <Button size="sm" variant="outline" className="rounded-full" onClick={() => setCall({ room: `recrutai-chat-${active.candidate_id}`, audioOnly: false })} data-testid="admin-video-call-btn"><Video className="h-4 w-4" /></Button>
                  <Button size="sm" variant="outline" className="rounded-full" onClick={() => setCall({ room: `recrutai-chat-${active.candidate_id}`, audioOnly: true })} data-testid="admin-audio-call-btn"><Phone className="h-4 w-4" /></Button>
                </div>
              </div>
              <div className="flex-1 overflow-y-auto p-4 space-y-2">
                {msgs.map((m) => (
                  <div key={m.id}>
                    {firstUnread === m.id && (
                      <div ref={unreadRef} className="flex items-center gap-2 my-2" data-testid="admin-unread-divider">
                        <div className="flex-1 h-px bg-primary/40" />
                        <span className="text-[10px] font-semibold text-primary uppercase tracking-wide">Nouveaux messages</span>
                        <div className="flex-1 h-px bg-primary/40" />
                      </div>
                    )}
                    <ChatMessageBubble m={m} mine={m.sender_role === "admin"} editable onEdit={editMsg} onDelete={deleteMsg} />
                  </div>
                ))}
                {otherTyping && <p className="text-xs text-muted-foreground italic animate-pulse" data-testid="admin-typing-indicator">{active?.candidate_name || "Le candidat"} est en train d'écrire…</p>}
              </div>
              <div className="p-3 border-t border-border flex items-center gap-2">
                <input ref={fileInputRef} type="file" accept="image/*,application/pdf,.doc,.docx,.txt,.xls,.xlsx" onChange={onPickFile} className="hidden" data-testid="admin-chat-file-input" />
                <button onClick={() => fileInputRef.current?.click()} disabled={uploading} data-testid="admin-attach-btn" title="Joindre un fichier" className="h-10 w-10 shrink-0 rounded-full border border-border flex items-center justify-center hover:bg-secondary transition-colors">
                  {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Paperclip className="h-4 w-4" />}
                </button>
                <button onClick={recording ? stopRec : startRec} data-testid="admin-voice-btn" title="Message vocal" className={`h-10 w-10 shrink-0 rounded-full border flex items-center justify-center transition-colors ${recording ? "bg-red-500 text-white border-red-500 animate-pulse" : "border-border hover:bg-secondary"}`}>
                  {recording ? <Square className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
                </button>
                <Input value={text} onChange={(e) => { setText(e.target.value); pingTyping(); }} onKeyDown={(e) => e.key === "Enter" && send()} placeholder="Répondre..." className="rounded-full" data-testid="admin-chat-input" />
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

function Contracts({ initialFilter }) {
  const [list, setList] = useState([]);
  const [filter, setFilter] = useState(initialFilter || "all");
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY_CONTRACT);
  const [del, setDel] = useState(null);
  const [search, setSearch] = useState("");
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
  const shown = list.filter((c) => { const q = search.trim().toLowerCase(); return !q || [c.title, c.client, c.candidate_name, c.job_title].some((v) => (v || "").toLowerCase().includes(q)); });

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

      {shown.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-16 text-center text-muted-foreground">Aucun contrat.</div>
      ) : (
        <div className="rounded-2xl border border-border bg-card overflow-hidden">
          <Table>
            <TableHeader><TableRow><TableHead>Intitulé</TableHead><TableHead>Client</TableHead><TableHead>Candidat</TableHead><TableHead>Montant</TableHead><TableHead>Statut</TableHead><TableHead className="text-right">Actions</TableHead></TableRow></TableHeader>
            <TableBody>
              {shown.map((c) => (
                <TableRow key={c.id} className="cursor-pointer" onClick={() => openEdit(c)} data-testid={`contract-row-${c.id}`}>
                  <TableCell className="font-medium">{c.title}</TableCell>
                  <TableCell className="text-muted-foreground">{c.client}</TableCell>
                  <TableCell className="text-muted-foreground">{c.candidate_name}</TableCell>
                  <TableCell>{c.amount}</TableCell>
                  <TableCell><span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${(C_STATUS[c.status] || C_STATUS.en_cours).c}`}>{(C_STATUS[c.status] || C_STATUS.en_cours).l}</span></TableCell>
                  <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
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

function Interviews() {
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

  const filtered = list.filter((i) => { const q = search.trim().toLowerCase(); return !q || [i.title, i.candidate_name, i.location].some((v) => (v || "").toLowerCase().includes(q)); });
  const groups = filtered.reduce((acc, i) => { (acc[i.date] = acc[i.date] || []).push(i); return acc; }, {});
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

function Meetings() {
  const [call, setCall] = useState(null);
  const start = () => setCall({ room: `recrutai-room-${Math.random().toString(36).slice(2, 10)}` });
  return (
    <div>
      {call && <VideoCall room={call.room} title="Salle de réunion" recordCtx={{ title: "Réunion" }} onClose={() => setCall(null)} />}
      <h1 className="font-display text-3xl font-semibold mb-2">Salle de réunion</h1>
      <p className="text-muted-foreground mb-6 max-w-xl">Démarrez une salle vidéo instantanée, partagez le lien d'invitation, et enregistrez la session pour générer automatiquement un résumé IA (visible dans « Enregistrements »).</p>
      <Button onClick={start} className="rounded-full h-11 px-6" data-testid="start-meeting-btn"><Video className="h-4 w-4 mr-2" /> Démarrer une salle</Button>
    </div>
  );
}

function Suggestions({ onOpenProfile, initialJob }) {
  const [jobs, setJobs] = useState([]);
  const [openJob, setOpenJob] = useState(null);
  const [sugg, setSugg] = useState({});
  const [loadingId, setLoadingId] = useState(null);

  useEffect(() => { api.get("/jobs/all").then(({ data }) => setJobs(data)).catch(() => {}); }, []);

  const loadSugg = useCallback(async (jobId) => {
    setOpenJob(jobId);
    setSugg((prev) => {
      if (prev[jobId]) return prev;
      setLoadingId(jobId);
      api.get(`/jobs/${jobId}/suggestions`)
        .then(({ data }) => setSugg((s) => ({ ...s, [jobId]: data })))
        .catch(() => toast.error("Impossible de charger les suggestions."))
        .finally(() => setLoadingId(null));
      return prev;
    });
  }, []);

  const toggle = (job) => {
    if (openJob === job.id) { setOpenJob(null); return; }
    loadSugg(job.id);
  };

  useEffect(() => {
    if (initialJob && jobs.some((j) => j.id === initialJob)) loadSugg(initialJob);
  }, [initialJob, jobs, loadSugg]);

  return (
    <div data-testid="suggestions-section">
      <h1 className="font-display text-3xl font-semibold mb-2">Suggestions IA</h1>
      <p className="text-muted-foreground mb-6">Pour chaque offre, l'IA analyse les profils des candidats et propose les plus pertinents, classés par score de compatibilité.</p>
      {jobs.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-16 text-center text-muted-foreground" data-testid="no-suggestions-jobs">
          <Sparkles className="h-12 w-12 text-muted-foreground/40 mx-auto mb-4" /> Publiez une offre pour obtenir des suggestions de candidats.
        </div>
      ) : (
        <div className="space-y-4">
          {jobs.map((job) => (
            <div key={job.id} className="rounded-2xl border border-border bg-card overflow-hidden" data-testid={`suggestion-job-${job.id}`}>
              <button onClick={() => toggle(job)} className="w-full flex items-center justify-between gap-4 p-5 text-left hover:bg-secondary/40 transition-colors" data-testid={`suggestion-toggle-${job.id}`}>
                <div className="min-w-0">
                  <h3 className="font-display text-lg font-semibold truncate">{job.title}</h3>
                  <p className="text-xs text-muted-foreground">{job.company || "—"} • {job.location}{!job.is_active ? " • (masquée)" : ""}</p>
                </div>
                <span className="inline-flex items-center gap-1.5 text-sm text-primary font-medium shrink-0"><Sparkles className="h-4 w-4" /> {openJob === job.id ? "Masquer" : "Voir les profils"}</span>
              </button>
              {openJob === job.id && (
                <div className="border-t border-border p-5 space-y-3">
                  {loadingId === job.id ? (
                    <div className="flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> Analyse IA des profils…</div>
                  ) : (sugg[job.id] || []).length === 0 ? (
                    <p className="text-sm text-muted-foreground">Aucun profil correspondant pour le moment.</p>
                  ) : (
                    sugg[job.id].map((c) => (
                      <div key={c.candidate_id} className="flex items-start gap-4 rounded-xl border border-border p-4" data-testid={`suggested-candidate-${c.candidate_id}`}>
                        <Avatar name={c.name} src={c.picture} size={44} onClick={() => onOpenProfile(c.candidate_id)} />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <button onClick={() => onOpenProfile(c.candidate_id)} className="font-medium hover:text-primary transition-colors" data-testid={`suggested-name-${c.candidate_id}`}>{c.name || "Candidat"}</button>
                            <span className="inline-flex items-center gap-1 rounded-full bg-primary/10 text-primary px-2.5 py-0.5 text-xs font-bold" data-testid={`suggested-score-${c.candidate_id}`}>{c.score}% compatible</span>
                          </div>
                          {c.current_position && <p className="text-xs text-muted-foreground">{c.current_position}</p>}
                          <p className="text-sm mt-1">{c.reason}</p>
                        </div>
                        <Button size="sm" variant="outline" className="rounded-full shrink-0" onClick={() => onOpenProfile(c.candidate_id)} data-testid={`suggested-view-${c.candidate_id}`}>Profil</Button>
                      </div>
                    ))
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function Recordings() {
  const [list, setList] = useState([]);
  const [del, setDel] = useState(null);
  const [copiedId, setCopiedId] = useState(null);
  const load = useCallback(() => api.get("/recordings").then(({ data }) => setList(data)).catch(() => {}), []);
  useEffect(() => { load(); const t = setInterval(load, 8000); return () => clearInterval(t); }, [load]);
  const remove = async () => { await api.delete(`/recordings/${del.id}`); toast.success("Enregistrement supprimé"); setDel(null); load(); };
  const shareLink = async (r) => {
    try {
      const { data } = await api.post(`/recordings/${r.id}/share`);
      const url = `${window.location.origin}/recordings/shared/${data.token}`;
      try { await navigator.clipboard.writeText(url); } catch { window.prompt("Copiez le lien :", url); }
      setCopiedId(r.id);
      setTimeout(() => setCopiedId(null), 2500);
      toast.success("Lien protégé copié (accès admin requis).");
    } catch {
      toast.error("Impossible de générer le lien.");
    }
  };

  return (
    <div>
      <h1 className="font-display text-3xl font-semibold mb-2">Enregistrements</h1>
      <p className="text-muted-foreground mb-6">Vidéos d'entretiens enregistrées, avec transcription et résumé IA automatiques.</p>
      {list.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-16 text-center text-muted-foreground" data-testid="no-recordings">
          <Film className="h-12 w-12 text-muted-foreground/40 mx-auto mb-4" />
          Aucun enregistrement. Lancez un appel ou une réunion et cliquez sur « Enregistrer ».
        </div>
      ) : (
        <div className="space-y-5">
          {list.map((r) => (
            <div key={r.id} className="rounded-2xl border border-border bg-card p-5" data-testid={`recording-${r.id}`}>
              <div className="flex items-start justify-between gap-4 mb-3 flex-wrap">
                <div>
                  <h3 className="font-display text-lg font-semibold">{r.title}</h3>
                  <p className="text-xs text-muted-foreground">{r.candidate_name ? `${r.candidate_name} • ` : ""}{new Date(r.created_at).toLocaleString("fr-FR")}</p>
                </div>
                <div className="flex items-center gap-2">
                  {r.status === "processing"
                    ? <span className="inline-flex items-center gap-1.5 rounded-full bg-secondary px-3 py-1 text-xs font-medium" data-testid={`rec-status-${r.id}`}><Loader2 className="h-3.5 w-3.5 animate-spin" /> Analyse IA…</span>
                    : <span className="inline-flex items-center gap-1.5 rounded-full status-accepted px-3 py-1 text-xs font-semibold" data-testid={`rec-status-${r.id}`}><CheckCircle2 className="h-3.5 w-3.5" /> Prêt</span>}
                  <Button variant="outline" size="sm" className="rounded-full" onClick={() => shareLink(r)} data-testid={`share-recording-${r.id}`}>
                    {copiedId === r.id ? <><Check className="h-4 w-4 mr-1.5 text-green-500" /> Copié</> : <><Link2 className="h-4 w-4 mr-1.5" /> Lien</>}
                  </Button>
                  <Button asChild variant="outline" size="sm" className="rounded-full" data-testid={`download-recording-${r.id}`}>
                    <a href={fileUrl(r.video_file_id)} download={`${(r.title || "entretien").replace(/[^a-z0-9]+/gi, "_")}.webm`}><Download className="h-4 w-4 mr-1.5" /> Vidéo</a>
                  </Button>
                  <Button variant="ghost" size="icon" onClick={() => setDel(r)} data-testid={`delete-recording-${r.id}`}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                </div>
              </div>
              <div className="grid md:grid-cols-2 gap-4">
                <video src={fileUrl(r.video_file_id)} controls className="w-full rounded-xl bg-black max-h-64" data-testid={`rec-video-${r.id}`} />
                <div className="space-y-3">
                  {r.summary ? (
                    <div className="rounded-xl bg-primary/5 border border-primary/20 p-3">
                      <p className="text-xs font-semibold text-primary mb-1 flex items-center gap-1.5"><Sparkles className="h-3.5 w-3.5" /> Résumé IA</p>
                      <p className="text-sm whitespace-pre-wrap" data-testid={`rec-summary-${r.id}`}>{r.summary}</p>
                    </div>
                  ) : r.status === "processing" ? (
                    <p className="text-sm text-muted-foreground">Le résumé IA sera disponible dans quelques instants…</p>
                  ) : (
                    <p className="text-sm text-muted-foreground">Aucune transcription disponible (audio manquant).</p>
                  )}
                  {r.transcript && (
                    <details className="rounded-xl bg-secondary/40 p-3">
                      <summary className="text-xs font-semibold cursor-pointer">Transcription complète</summary>
                      <p className="text-sm text-muted-foreground whitespace-pre-wrap mt-2">{r.transcript}</p>
                    </details>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
      <AlertDialog open={!!del} onOpenChange={() => setDel(null)}>
        <AlertDialogContent>
          <AlertDialogHeader><AlertDialogTitle>Supprimer cet enregistrement ?</AlertDialogTitle><AlertDialogDescription>La vidéo et son résumé seront supprimés définitivement.</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter><AlertDialogCancel>Annuler</AlertDialogCancel><AlertDialogAction onClick={remove} data-testid="confirm-delete-recording">Supprimer</AlertDialogAction></AlertDialogFooter>
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
