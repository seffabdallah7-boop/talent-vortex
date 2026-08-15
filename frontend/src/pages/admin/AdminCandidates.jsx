import { useState, useEffect, useCallback, Fragment } from "react";
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
import { Star, Trash2, CheckSquare, ChevronDown, Loader2, ExternalLink } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";

const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const Highlight = ({ text, q }) => {
  if (!q || !text) return text || null;
  const parts = String(text).split(new RegExp(`(${escapeRe(q.trim())})`, "ig"));
  return parts.map((p, i) =>
    p.toLowerCase() === q.trim().toLowerCase()
      ? <mark key={i} className="bg-primary/25 text-foreground rounded px-0.5">{p}</mark>
      : <span key={i}>{p}</span>
  );
};

export default function Candidates({ onOpenProfile }) {
  const { user: me } = useAuth();
  const [list, setList] = useState([]);
  const [del, setDel] = useState(null);
  const [q, setQ] = useState("");
  const [minRating, setMinRating] = useState("all");
  const [nats, setNats] = useState([]);
  const [natFilter, setNatFilter] = useState("");
  const [natOpen, setNatOpen] = useState(false);
  const [cvView, setCvView] = useState(null);
  const openCv = async (u) => {
    setCvView({ user: u, loading: true, text: "" });
    try {
      const { data } = await api.get(`/users/${u.user_id}/cv-text`);
      setCvView({ user: u, loading: false, text: data.cv_text || "", cv_file_id: data.cv_file_id, cv_filename: data.cv_filename });
    } catch (e) {
      toast.error("Impossible de charger le CV");
      setCvView(null);
    }
  };
  const openOriginalCv = async () => {
    if (!cvView?.cv_file_id) return;
    try {
      const { data } = await api.get(`/files/${cvView.cv_file_id}`, { responseType: "blob" });
      window.open(URL.createObjectURL(data), "_blank");
    } catch (e) { toast.error("Impossible d'ouvrir le CV original"); }
  };
  const visibleList = list.filter((u) => !me || u.user_id !== me.user_id);
  const filteredList = natFilter ? visibleList.filter((u) => (u.nationality || "") === natFilter) : visibleList;
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
                      {me?.is_super && u.is_super && <span className="ml-1 rounded-full bg-amber-500/15 text-amber-600 px-2 py-0.5 text-[10px] font-semibold" data-testid={`super-badge-${u.user_id}`}>Super</span>}
                    </TableCell>
                    <TableCell><span className="rounded-full bg-secondary px-2.5 py-0.5 text-xs font-medium">{u.application_count}</span></TableCell>
                    <TableCell className="text-right">
                      {!isSelf && u.role === "candidate" && (
                        <Button variant="outline" size="sm" className="rounded-full mr-2" onClick={() => changeRole(u, "admin")} data-testid={`promote-${u.user_id}`}>Promouvoir admin</Button>
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

      <Dialog open={!!cvView} onOpenChange={(o) => !o && setCvView(null)}>
        <DialogContent className="max-w-2xl" data-testid="cv-preview-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 flex-wrap">
              Aperçu du CV — {cvView?.user?.name}
              {cvView?.cv_file_id && (
                <Button variant="outline" size="sm" className="rounded-full ml-auto" onClick={openOriginalCv} data-testid="open-original-cv-btn">
                  <ExternalLink className="h-3.5 w-3.5 mr-1.5" /> CV original
                </Button>
              )}
            </DialogTitle>
          </DialogHeader>
          {cvView?.loading ? (
            <div className="flex items-center justify-center py-12 text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin mr-2" /> Chargement…</div>
          ) : cvView?.text ? (
            <div className="max-h-[60vh] overflow-y-auto whitespace-pre-wrap text-sm leading-relaxed rounded-lg border border-border bg-secondary/20 p-4" data-testid="cv-preview-text">
              <Highlight text={cvView.text} q={q} />
            </div>
          ) : (
            <p className="text-sm text-muted-foreground py-8 text-center">Aucun texte exploitable dans ce CV.</p>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
