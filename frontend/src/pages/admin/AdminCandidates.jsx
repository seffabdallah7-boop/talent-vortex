import { useState, useEffect, useCallback, useRef, Fragment } from "react";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import { Table, TableHeader, TableRow, TableHead, TableBody, TableCell } from "@/components/ui/table";
import {
  AlertDialog, AlertDialogContent, AlertDialogHeader, AlertDialogTitle, AlertDialogDescription,
  AlertDialogFooter, AlertDialogCancel, AlertDialogAction,
} from "@/components/ui/alert-dialog";
import { Avatar } from "@/components/Avatar";
import { Checkbox } from "@/components/ui/checkbox";
import { useListControls } from "@/hooks/useListControls";
import { Pager, BulkBar } from "@/components/ListControls";
import { Star, Trash2, CheckSquare, ChevronDown, Loader2, ExternalLink, Sparkles, Mic, MicOff, Send, ScanLine, RefreshCw, CheckCircle2, AlertCircle } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";

const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const Highlight = ({ text, q }) => {
  if (!q || !text) return text || null;
  const parts = String(text).split(new RegExp(`(${escapeRe(q.trim())})`, "ig"));
  return parts.map((p, i) =>
    p.toLowerCase() === q.trim().toLowerCase()
      ? <mark key={`${i}-${p}`} className="bg-primary/25 text-foreground rounded px-0.5">{p}</mark>
      : <span key={`${i}-${p}`}>{p}</span>
  );
};

export default function Candidates({ onOpenProfile }) {
  const { user: me } = useAuth();
  const [list, setList] = useState([]);
  const [del, setDel] = useState(null);
  const [promote, setPromote] = useState(null);
  const [q, setQ] = useState("");
  const [minRating, setMinRating] = useState("all");
  const [nats, setNats] = useState([]);
  const [natFilter, setNatFilter] = useState("");
  const [ivFilter, setIvFilter] = useState("all");
  const [cvFilter, setCvFilter] = useState("all");
  const [natOpen, setNatOpen] = useState(false);
  const [cvView, setCvView] = useState(null);
  const [aiQuery, setAiQuery] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [aiMessages, setAiMessages] = useState([]);
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef(null);
  const aiScrollRef = useRef(null);
  const [scan, setScan] = useState(null);
  const [scanning, setScanning] = useState(false);
  const speechSupported = typeof window !== "undefined" && (window.SpeechRecognition || window.webkitSpeechRecognition);

  const loadScan = useCallback(() => api.get("/cv-scan/status").then(({ data }) => setScan(data)).catch(() => {}), []);
  useEffect(() => { loadScan(); }, [loadScan]);
  useEffect(() => {
    if (!scan?.running) return;
    const t = setInterval(loadScan, 4000);
    return () => clearInterval(t);
  }, [scan?.running, loadScan]);
  const runScanAll = async (force = false) => {
    setScanning(true);
    try {
      const { data } = await api.post(`/cv-scan/all?force=${force}`);
      if (data.status === "busy") toast.info("Un scan est déjà en cours.");
      else { toast.success("Scan des CV lancé en arrière-plan."); setScan((s) => ({ ...(s || {}), running: true })); }
      setTimeout(loadScan, 1500);
    } catch (e) { toast.error("Impossible de lancer le scan."); }
    finally { setScanning(false); }
  };

  useEffect(() => {
    if (aiScrollRef.current) aiScrollRef.current.scrollTop = aiScrollRef.current.scrollHeight;
  }, [aiMessages, aiLoading]);

  const runAiSearch = async () => {
    const query = aiQuery.trim();
    if (!query || aiLoading) return;
    const history = aiMessages.map((m) => ({ role: m.role, content: m.content }));
    setAiMessages((prev) => [...prev, { role: "user", content: query }]);
    setAiQuery("");
    setAiLoading(true);
    try {
      const { data } = await api.post("/users/ai-search", { query, history });
      setAiMessages((prev) => [...prev, {
        role: "assistant",
        content: data.answer || "Voici les candidats correspondants.",
        results: data.results || [],
      }]);
    } catch (e) {
      toast.error(formatApiError(e.response?.data?.detail) || "Recherche IA indisponible");
      setAiMessages((prev) => [...prev, { role: "assistant", content: "Désolé, la recherche IA est momentanément indisponible.", results: [] }]);
    } finally { setAiLoading(false); }
  };
  const clearAiChat = () => { setAiMessages([]); setAiQuery(""); };
  const toggleMic = () => {
    if (!speechSupported) { toast.error("La saisie vocale n'est pas supportée par ce navigateur (utilisez Chrome ou Edge)."); return; }
    if (listening) { recognitionRef.current?.stop(); return; }
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    const rec = new SR();
    rec.lang = "fr-FR";
    rec.interimResults = true;
    rec.continuous = false;
    rec.onstart = () => setListening(true);
    rec.onerror = () => { setListening(false); };
    rec.onend = () => setListening(false);
    rec.onresult = (ev) => {
      let txt = "";
      for (let i = 0; i < ev.results.length; i++) txt += ev.results[i][0].transcript;
      setAiQuery(txt);
    };
    recognitionRef.current = rec;
    rec.start();
  };
  const openCv = async (u) => {
    setCvView({ user: u, loading: true, text: "" });
    try {
      const [{ data }, sc] = await Promise.all([
        api.get(`/users/${u.user_id}/cv-text`),
        api.get(`/cv-scan/${u.user_id}/data`).catch(() => ({ data: null })),
      ]);
      setCvView({
        user: u, loading: false, text: data.cv_text || "",
        cv_file_id: data.cv_file_id, cv_filename: data.cv_filename,
        structured: sc?.data?.structured || null, scanStatus: sc?.data?.status || null,
      });
    } catch (e) {
      toast.error("Impossible de charger le CV");
      setCvView(null);
    }
  };
  const rescanCv = async (u) => {
    toast.info("Re-scan du CV en cours…");
    try {
      await api.post(`/cv-scan/${u.user_id}?force=true`);
      toast.success("CV re-scanné");
      openCv(u); loadScan();
    } catch (e) { toast.error("Échec du re-scan"); }
  };
  const openOriginalCv = async () => {
    if (!cvView?.cv_file_id) return;
    try {
      const { data } = await api.get(`/files/${cvView.cv_file_id}`, { responseType: "blob" });
      window.open(URL.createObjectURL(data), "_blank");
    } catch (e) { toast.error("Impossible d'ouvrir le CV original"); }
  };
  const visibleList = list.filter((u) => !me || u.user_id !== me.user_id);
  const filteredList = (natFilter ? visibleList.filter((u) => (u.nationality || "") === natFilter) : visibleList)
    .filter((u) => ivFilter === "all" ? true : u.interview_status === ivFilter)
    .filter((u) => {
      if (cvFilter === "all") return true;
      if (cvFilter === "scanned") return u.cv_scanned;
      if (cvFilter === "unscanned") return u.has_cv && !u.cv_scanned;
      return true;
    });
  const lc = useListControls(filteredList, { pageSize: 15, selectId: (u) => u.user_id });
  const bulkDelete = async () => {
    const ids = lc.selectedIds();
    if (ids.length === 0) return;
    if (!window.confirm(`Supprimer ${ids.length} utilisateur(s) ? Les comptes protégés seront ignorés.`)) return;
    await Promise.all(ids.map((id) => api.delete(`/users/${id}`).catch(() => {})));
    toast.success("Suppression effectuée");
    lc.clear(); load();
  };
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
    finally { setPromote(null); }
  };
  const toggleSuper = async (u) => {
    try {
      await api.put(`/users/${u.user_id}/super`, { is_super: !u.is_super });
      toast.success(!u.is_super ? `${u.name} est désormais super admin` : `Statut super admin retiré à ${u.name}`);
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
            <Input data-testid="candidate-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher (nom, email, domaine, contenu du CV...)" className="rounded-full" />
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
      <div className="rounded-2xl border border-emerald-500/30 bg-emerald-500/5 p-4 mb-6" data-testid="cv-scan-panel">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <ScanLine className="h-4 w-4 text-emerald-600" />
            <span className="text-sm font-semibold">Scanning IA des CV — extraction structurée (compétences, expériences, formations…)</span>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="icon" className="rounded-full h-8 w-8" onClick={loadScan} data-testid="cv-scan-refresh" title="Rafraîchir"><RefreshCw className="h-4 w-4" /></Button>
            <Button onClick={() => runScanAll(false)} disabled={scanning || scan?.running} className="rounded-full bg-emerald-600 hover:bg-emerald-700" data-testid="cv-scan-all-btn">
              {(scanning || scan?.running) ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <ScanLine className="h-4 w-4 mr-2" />}
              {scan?.running ? "Scan en cours…" : "Scanner les CV non scannés"}
            </Button>
            <Button variant="outline" onClick={() => runScanAll(true)} disabled={scanning || scan?.running} className="rounded-full" data-testid="cv-scan-force-btn">Tout re-scanner</Button>
          </div>
        </div>
        {scan && (
          <div className="flex items-center gap-4 mt-3 text-sm flex-wrap" data-testid="cv-scan-stats">
            <span className="inline-flex items-center gap-1.5 text-muted-foreground">CV total : <b className="text-foreground">{scan.total_cv}</b></span>
            <span className="inline-flex items-center gap-1.5 text-emerald-600"><CheckCircle2 className="h-4 w-4" /> Scannés : <b>{scan.scanned}</b></span>
            <span className="inline-flex items-center gap-1.5 text-amber-600">À scanner : <b>{scan.pending}</b></span>
            {scan.errors > 0 && <span className="inline-flex items-center gap-1.5 text-destructive"><AlertCircle className="h-4 w-4" /> Erreurs : <b>{scan.errors}</b></span>}
          </div>
        )}
      </div>
      <div className="rounded-2xl border border-primary/30 bg-primary/5 p-4 mb-6" data-testid="ai-search-panel">
        <div className="flex items-center justify-between gap-2 mb-3">
          <div className="flex items-center gap-2"><Sparkles className="h-4 w-4 text-primary" /><span className="text-sm font-semibold">Agent IA conversationnel — analyse des profils & du contenu des CV</span></div>
          {aiMessages.length > 0 && <Button variant="ghost" size="sm" onClick={clearAiChat} className="rounded-full text-xs h-7" data-testid="ai-search-clear">Nouvelle conversation</Button>}
        </div>
        {aiMessages.length > 0 && (
          <div ref={aiScrollRef} className="max-h-[46vh] overflow-y-auto space-y-3 mb-3 pr-1" data-testid="ai-chat-thread">
            {aiMessages.map((m, i) => (
              <div key={`${i}-${m.role}`} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                <div className={`max-w-[85%] ${m.role === "user" ? "" : "w-full"}`}>
                  <div className={`rounded-2xl px-3.5 py-2.5 text-sm ${m.role === "user" ? "bg-primary text-primary-foreground rounded-br-sm" : "bg-card border border-border rounded-bl-sm"}`} data-testid={`ai-msg-${m.role}-${i}`}>
                    {m.content}
                  </div>
                  {m.role === "assistant" && m.results && m.results.length > 0 && (
                    <div className="mt-2 space-y-2" data-testid={`ai-results-${i}`}>
                      {m.results.map((r) => (
                        <div key={r.user_id} className="rounded-xl border border-border bg-card p-3 flex items-start justify-between gap-3" data-testid={`ai-result-${r.user_id}`}>
                          <div className="min-w-0">
                            <div className="flex items-center gap-2 flex-wrap"><span className="font-semibold">{r.name}</span><span className="text-xs rounded-full bg-primary/15 text-primary px-2 py-0.5 font-bold">{r.ai_score}%</span><span className="text-xs text-muted-foreground truncate">{r.email}</span></div>
                            <p className="text-sm text-muted-foreground mt-0.5">{r.ai_reason}</p>
                          </div>
                          <Button size="sm" variant="outline" className="rounded-full shrink-0" onClick={() => onOpenProfile?.(r.user_id)} data-testid={`ai-open-${r.user_id}`}>Voir le profil</Button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {aiLoading && (
              <div className="flex justify-start" data-testid="ai-typing">
                <div className="rounded-2xl rounded-bl-sm px-3.5 py-2.5 text-sm bg-card border border-border flex items-center gap-2 text-muted-foreground"><Loader2 className="h-3.5 w-3.5 animate-spin" /> L'agent analyse les CV…</div>
              </div>
            )}
          </div>
        )}
        <div className="flex gap-2 items-center">
          {speechSupported && (
            <Button type="button" onClick={toggleMic} variant={listening ? "default" : "outline"} size="icon" className={`rounded-full shrink-0 ${listening ? "animate-pulse" : ""}`} data-testid="ai-mic-btn" title={listening ? "Arrêter la dictée" : "Dicter la requête"}>
              {listening ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
            </Button>
          )}
          <Input data-testid="ai-search-input" value={aiQuery} onChange={(e) => setAiQuery(e.target.value)} onKeyDown={(e) => e.key === "Enter" && runAiSearch()} placeholder={listening ? "Parlez maintenant…" : "Ex : qui a de l'expérience React et connaît Docker ?"} className="rounded-full flex-1 min-w-[220px] bg-background" />
          <Button onClick={runAiSearch} disabled={aiLoading || !aiQuery.trim()} className="rounded-full shrink-0" data-testid="ai-search-btn">{aiLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}<span className="hidden sm:inline ml-2">Envoyer</span></Button>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3 mb-4" data-testid="user-filters">
        <label className="text-xs text-muted-foreground">Entretien
          <select value={ivFilter} onChange={(e) => setIvFilter(e.target.value)} data-testid="filter-interview" className="ml-2 rounded-full border border-border bg-background px-3 py-1.5 text-sm">
            <option value="all">Tous</option>
            <option value="interview_scheduled">Entretien fixé</option>
            <option value="interview_done">Entretien fait</option>
          </select>
        </label>
        <label className="text-xs text-muted-foreground">Scan CV
          <select value={cvFilter} onChange={(e) => setCvFilter(e.target.value)} data-testid="filter-cvscan" className="ml-2 rounded-full border border-border bg-background px-3 py-1.5 text-sm">
            <option value="all">Tous</option>
            <option value="scanned">CV bien scanné</option>
            <option value="unscanned">CV non scanné</option>
          </select>
        </label>
      </div>
      {nats.length > 0 && (
        <div className="rounded-2xl border border-border bg-card p-4 mb-6" data-testid="nationalities-panel">
          <button type="button" onClick={() => setNatOpen((o) => !o)} data-testid="toggle-nationalities" className="flex items-center gap-2 w-full text-left">
            <ChevronDown className={`h-4 w-4 transition-transform ${natOpen ? "" : "-rotate-90"}`} />
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">Répartition par nationalité</span>
            {natFilter && <span onClick={(e) => { e.stopPropagation(); setNatFilter(""); }} className="ml-auto text-xs text-primary hover:underline" data-testid="nat-clear-filter">Filtre : {natFilter} ✕</span>}
          </button>
          {natOpen && (
            <div className="flex flex-wrap gap-2 mt-3">
              {nats.map((n) => (
                <button key={n.nationality} type="button" data-testid={`nat-${n.nationality}`} onClick={() => setNatFilter((f) => f === n.nationality ? "" : n.nationality)} className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm transition-colors ${natFilter === n.nationality ? "bg-primary text-primary-foreground" : "bg-secondary hover:bg-primary/10"}`}>
                  {n.nationality}
                  <span className={`rounded-full px-1.5 text-xs font-bold ${natFilter === n.nationality ? "bg-white/20" : "bg-primary/15 text-primary"}`}>{n.count}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      {filteredList.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border p-16 text-center text-muted-foreground">Aucun utilisateur.</div>
      ) : (
        <>
        <div className="mb-3 flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2">
            <Button variant={lc.selectMode ? "default" : "outline"} size="sm" className="rounded-full" onClick={lc.toggleSelectMode} data-testid="toggle-select-mode"><CheckSquare className="h-4 w-4 mr-2" /> {lc.selectMode ? "Annuler" : "Sélectionner"}</Button>
            {lc.selectMode && <BulkBar count={lc.selectedCount} onDelete={bulkDelete} onClear={lc.clear} testId="users-bulk" />}
          </div>
          <Pager page={lc.page} totalPages={lc.totalPages} total={lc.total} onPage={lc.setPage} testId="users-pager-top" />
        </div>
        <div className="rounded-2xl border border-border bg-card overflow-hidden">
          <Table>
            <TableHeader><TableRow>{lc.selectMode && <TableHead className="w-10"><Checkbox checked={lc.allPageSelected} onCheckedChange={lc.toggleAllPage} data-testid="select-all-users" /></TableHead>}<TableHead>Nom</TableHead><TableHead>Email</TableHead><TableHead>Nationalité</TableHead><TableHead>Poste</TableHead><TableHead>Appréciation</TableHead><TableHead>Rôle</TableHead><TableHead>Cand.</TableHead><TableHead className="text-right">Actions</TableHead></TableRow></TableHeader>
            <TableBody>
              {lc.pageItems.map((u) => {
                const isSelf = me && u.user_id === me.user_id;
                return (
                  <Fragment key={u.user_id}>
                  <TableRow data-testid={`candidate-row-${u.user_id}`}>
                    {lc.selectMode && <TableCell className="w-10"><Checkbox checked={lc.selected.has(u.user_id)} onCheckedChange={() => lc.toggle(u.user_id)} data-testid={`select-user-${u.user_id}`} /></TableCell>}
                    <TableCell className="font-medium">
                      <button className="flex items-center gap-3 hover:opacity-80 text-left" onClick={() => onOpenProfile(u.user_id)} data-testid={`open-profile-${u.user_id}`}>
                        <Avatar name={u.name} src={u.picture} size={36} />
                        <span className="flex flex-col gap-1">
                          <span>{u.name} {isSelf && <span className="text-xs text-muted-foreground">(vous)</span>}</span>
                          <span className="flex items-center gap-1.5 flex-wrap">
                            {u.interview_status === "interview_scheduled" && <span className="rounded-full bg-blue-500/15 text-blue-600 px-2 py-0.5 text-[10px] font-semibold" data-testid={`badge-interview-scheduled-${u.user_id}`}>Entretien fixé</span>}
                            {u.interview_status === "interview_done" && <span className="rounded-full bg-purple-500/15 text-purple-600 px-2 py-0.5 text-[10px] font-semibold" data-testid={`badge-interview-done-${u.user_id}`}>Entretien fait</span>}
                            {u.role === "candidate" && u.has_cv && (u.cv_scanned
                              ? <span title="CV scanned" className="rounded-full bg-emerald-500/15 text-emerald-600 px-2 py-0.5 text-[10px] font-bold" data-testid={`badge-cv-scanned-${u.user_id}`}>CV</span>
                              : <span title="CV not scanned" className="rounded-full bg-destructive/15 text-destructive px-2 py-0.5 text-[10px] font-bold" data-testid={`badge-cv-unscanned-${u.user_id}`}>CV</span>)}
                          </span>
                        </span>
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
                      {me?.is_super && u.is_super && <span className="ml-1 rounded-full bg-amber-500/15 text-amber-600 px-2 py-0.5 text-[10px] font-semibold" data-testid={`super-badge-${u.user_id}`}>Super</span>}
                    </TableCell>
                    <TableCell><span className="rounded-full bg-secondary px-2.5 py-0.5 text-xs font-medium">{u.application_count}</span></TableCell>
                    <TableCell className="text-right">
                      {!isSelf && u.role === "candidate" && (
                        <Button variant="outline" size="sm" className="rounded-full mr-2" onClick={() => setPromote(u)} data-testid={`promote-${u.user_id}`}>Promouvoir admin</Button>
                      )}
                      {!isSelf && u.role === "admin" && (
                        <Button variant="outline" size="sm" className="rounded-full mr-2" onClick={() => changeRole(u, "candidate")} data-testid={`demote-${u.user_id}`}>Rétrograder</Button>
                      )}
                      {me?.is_super && !isSelf && u.role === "admin" && (
                        <Button variant="outline" size="sm" className="rounded-full mr-2" onClick={() => toggleSuper(u)} data-testid={`super-${u.user_id}`}>{u.is_super ? "Retirer super" : "Super admin"}</Button>
                      )}
                      {!isSelf && (
                        <Button variant="ghost" size="icon" onClick={() => setDel(u)} data-testid={`delete-candidate-${u.user_id}`}><Trash2 className="h-4 w-4 text-destructive" /></Button>
                      )}
                    </TableCell>
                  </TableRow>
                  {u.cv_snippet && (
                    <TableRow data-testid={`cv-snippet-row-${u.user_id}`} className="bg-secondary/30 hover:bg-secondary/30">
                      <TableCell colSpan={9} className="py-2 text-xs text-muted-foreground">
                        <button type="button" onClick={() => openCv(u)} className="text-left hover:opacity-80" data-testid={`cv-snippet-${u.user_id}`}>
                          <span className="font-semibold text-foreground/70 mr-1">CV :</span>
                          <Highlight text={u.cv_snippet} q={q} />
                          <span className="ml-1 text-primary font-medium">(voir tout)</span>
                        </button>
                      </TableCell>
                    </TableRow>
                  )}
                  </Fragment>
                );
              })}
            </TableBody>
          </Table>
        </div>
        <Pager page={lc.page} totalPages={lc.totalPages} total={lc.total} onPage={lc.setPage} testId="users-pager" />
        </>
      )}
      <AlertDialog open={!!del} onOpenChange={() => setDel(null)}>
        <AlertDialogContent>
          <AlertDialogHeader><AlertDialogTitle>Supprimer {del?.name} ?</AlertDialogTitle><AlertDialogDescription>L'utilisateur et toutes ses candidatures seront supprimés définitivement.</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter><AlertDialogCancel>Annuler</AlertDialogCancel><AlertDialogAction onClick={remove} data-testid="confirm-delete-candidate">Supprimer</AlertDialogAction></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={!!promote} onOpenChange={() => setPromote(null)}>
        <AlertDialogContent>
          <AlertDialogHeader><AlertDialogTitle>Nommer {promote?.name} administrateur ?</AlertDialogTitle><AlertDialogDescription>Cette personne aura un accès complet à l'espace administrateur (offres, candidatures, candidats, messagerie). Êtes-vous sûr ?</AlertDialogDescription></AlertDialogHeader>
          <AlertDialogFooter><AlertDialogCancel>Annuler</AlertDialogCancel><AlertDialogAction onClick={() => changeRole(promote, "admin")} data-testid="confirm-promote-admin">Oui, nommer administrateur</AlertDialogAction></AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <Dialog open={!!cvView} onOpenChange={(o) => !o && setCvView(null)}>
        <DialogContent className="max-w-2xl" data-testid="cv-preview-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 flex-wrap">
              Aperçu du CV — {cvView?.user?.name}
              <div className="flex items-center gap-2 ml-auto">
                <Button variant="outline" size="sm" className="rounded-full" onClick={() => cvView?.user && rescanCv(cvView.user)} data-testid="cv-rescan-btn">
                  <ScanLine className="h-3.5 w-3.5 mr-1.5" /> Re-scanner
                </Button>
                {cvView?.cv_file_id && (
                  <Button variant="outline" size="sm" className="rounded-full" onClick={openOriginalCv} data-testid="open-original-cv-btn">
                    <ExternalLink className="h-3.5 w-3.5 mr-1.5" /> CV original
                  </Button>
                )}
              </div>
            </DialogTitle>
          </DialogHeader>
          {cvView?.loading ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin mr-2" /> Chargement…</div>
          ) : (
            <div className="max-h-[68vh] overflow-y-auto space-y-4" data-testid="cv-preview-body">
              {cvView?.structured ? (
                <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4 space-y-3" data-testid="cv-structured">
                  <div className="flex items-center gap-2 text-sm font-semibold text-emerald-700"><ScanLine className="h-4 w-4" /> Données extraites par l'IA</div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
                    {cvView.structured.current_position && <div><span className="text-muted-foreground">Poste : </span><b>{cvView.structured.current_position}</b></div>}
                    {cvView.structured.years_experience ? <div><span className="text-muted-foreground">Expérience : </span><b>{cvView.structured.years_experience} ans</b></div> : null}
                    {cvView.structured.email && <div><span className="text-muted-foreground">Email : </span>{cvView.structured.email}</div>}
                    {cvView.structured.phone && <div><span className="text-muted-foreground">Téléphone : </span>{cvView.structured.phone}</div>}
                  </div>
                  {cvView.structured.summary && <p className="text-sm text-muted-foreground italic">{cvView.structured.summary}</p>}
                  {(cvView.structured.skills || []).length > 0 && (
                    <div>
                      <div className="text-xs font-semibold text-muted-foreground uppercase mb-1.5">Compétences</div>
                      <div className="flex flex-wrap gap-1.5">
                        {cvView.structured.skills.map((s, i) => <span key={`${i}-${s}`} className="rounded-full bg-emerald-500/15 text-emerald-700 px-2.5 py-0.5 text-xs font-medium">{s}</span>)}
                      </div>
                    </div>
                  )}
                  {(cvView.structured.experiences || []).length > 0 && (
                    <div>
                      <div className="text-xs font-semibold text-muted-foreground uppercase mb-1.5">Expériences</div>
                      <div className="space-y-1.5">
                        {cvView.structured.experiences.map((e, i) => (
                          <div key={`${i}-${e.company}`} className="text-sm">
                            <b>{e.title}</b>{e.company ? ` — ${e.company}` : ""} {(e.start || e.end) && <span className="text-muted-foreground text-xs">({e.start} → {e.end || "…"})</span>}
                            {e.description && <p className="text-muted-foreground text-xs mt-0.5">{e.description}</p>}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                  {(cvView.structured.education || []).length > 0 && (
                    <div>
                      <div className="text-xs font-semibold text-muted-foreground uppercase mb-1.5">Formations</div>
                      {cvView.structured.education.map((e, i) => <div key={`${i}-${e.school}`} className="text-sm"><b>{e.degree}</b>{e.school ? ` — ${e.school}` : ""} {e.year && <span className="text-muted-foreground text-xs">({e.year})</span>}</div>)}
                    </div>
                  )}
                  {(cvView.structured.languages || []).length > 0 && (
                    <div className="text-sm"><span className="text-xs font-semibold text-muted-foreground uppercase">Langues : </span>{cvView.structured.languages.join(", ")}</div>
                  )}
                </div>
              ) : cvView?.scanStatus === "error" ? (
                <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive flex items-center gap-2"><AlertCircle className="h-4 w-4" /> Échec du scan de ce CV. Cliquez « Re-scanner » pour réessayer.</div>
              ) : (
                <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-sm text-amber-700">Ce CV n'a pas encore été scanné. Cliquez « Re-scanner » pour extraire les données.</div>
              )}
              {cvView?.text ? (
                <div>
                  <div className="text-xs font-semibold text-muted-foreground uppercase mb-1.5">Texte brut du CV</div>
                  <div className="whitespace-pre-wrap text-sm leading-relaxed rounded-lg border border-border bg-secondary/20 p-4" data-testid="cv-preview-text">
                    <Highlight text={cvView.text} q={q} />
                  </div>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground py-2 text-center">Aucun texte brut exploitable dans ce CV.</p>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
