import { useState, useEffect, useCallback } from "react";
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
import { Star, Trash2 } from "lucide-react";
import { toast } from "sonner";

export default function Candidates({ onOpenProfile }) {
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
