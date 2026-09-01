import { useEffect, useState } from "react";
import api, { fileUrl } from "@/lib/api";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Avatar } from "@/components/Avatar";
import { WhatsappIcon } from "@/components/WhatsappInput";
import ImageLightbox from "@/components/ImageLightbox";
import StatusBadge from "@/components/StatusBadge";
import {
  Loader2, Mail, Phone, MapPin, Briefcase, Globe, Star, CalendarDays,
  FileText, ScrollText, Sparkles, Clock, MessageSquare, Video,
} from "lucide-react";

const fmtDate = (d) => {
  try { return new Date(d).toLocaleDateString("fr-FR", { day: "numeric", month: "long", year: "numeric" }); }
  catch { return d; }
};

function Chips({ items, variant = "secondary" }) {
  if (!items || items.length === 0) return <span className="text-sm text-muted-foreground">Non renseigné</span>;
  const cls = variant === "primary" ? "bg-primary/10 text-primary" : "bg-secondary text-foreground";
  return (
    <div className="flex flex-wrap gap-1.5">
      {items.map((it, i) => (
        <span key={`${it}-${i}`} className={`rounded-full px-2.5 py-1 text-xs font-medium ${cls}`}>{it}</span>
      ))}
    </div>
  );
}

export default function CandidateProfileDialog({ userId, open, onClose, onChat, onCall }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [photoOpen, setPhotoOpen] = useState(false);
  const [jobs, setJobs] = useState([]);
  const [addOpen, setAddOpen] = useState(false);
  const [njob, setNjob] = useState("");
  const [nstatus, setNstatus] = useState("interview_scheduled");
  const [adding, setAdding] = useState(false);

  const reload = () => api.get(`/users/${userId}`).then(({ data }) => setData(data)).catch(() => {});
  useEffect(() => {
    if (open && userId) {
      setLoading(true);
      setData(null);
      setError(false);
      api.get(`/users/${userId}`).then(({ data }) => setData(data)).catch(() => setError(true)).finally(() => setLoading(false));
      api.get("/jobs/all").then(({ data }) => setJobs(data || [])).catch(() => {});
    }
  }, [open, userId]);
  const addApplication = async () => {
    if (!njob) { toast.error("Choisissez une offre"); return; }
    setAdding(true);
    try {
      await api.post("/applications/admin-create", { candidate_id: userId, job_id: njob, status: nstatus });
      toast.success("Candidature créée");
      setAddOpen(false); setNjob("");
      reload();
    } catch (e) { toast.error("Échec de la création"); }
    finally { setAdding(false); }
  };

  const u = data?.user;
  const apps = data?.applications || [];
  const interviews = data?.interviews || [];
  const contracts = data?.contracts || [];

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="candidate-profile-dialog">
        <DialogHeader className="sr-only"><DialogTitle>Profil du candidat</DialogTitle><DialogDescription>Détails du profil, expertise et candidatures du candidat.</DialogDescription></DialogHeader>
        {loading ? (
          <div className="flex justify-center py-24"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
        ) : error || !u ? (
          <div className="py-20 text-center text-muted-foreground" data-testid="profile-error">Impossible de charger ce profil.</div>
        ) : (
          <div className="space-y-6">
            {/* Header */}
            <div className="flex items-start gap-4">
              <Avatar name={u.name} src={u.picture} size={72} testId="profile-avatar" onClick={u.picture ? () => setPhotoOpen(true) : undefined} />
              <ImageLightbox src={u.picture} alt={u.name} open={photoOpen} onClose={() => setPhotoOpen(false)} />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <h2 className="font-display text-2xl font-semibold" data-testid="profile-name-heading">{u.name || "Sans nom"}</h2>
                  <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${u.role === "admin" ? "bg-primary/15 text-primary" : "bg-secondary text-muted-foreground"}`}>
                    {u.role === "admin" ? "Administrateur" : "Candidat"}
                  </span>
                </div>
                {(u.headline || u.current_position) && (
                  <p className="text-muted-foreground mt-0.5">{u.headline || u.current_position}</p>
                )}
                <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-sm text-muted-foreground">
                  <span className="flex items-center gap-1.5"><Mail className="h-3.5 w-3.5" /> {u.email}</span>
                  {u.phone && <span className="flex items-center gap-1.5"><Phone className="h-3.5 w-3.5" /> {u.phone}</span>}
                  {u.whatsapp && <a href={`https://wa.me/${u.whatsapp.replace(/\D/g, "")}`} target="_blank" rel="noreferrer" className="flex items-center gap-1.5 text-green-600 hover:underline font-medium" data-testid="profile-whatsapp-link" title="Écrire sur WhatsApp"><WhatsappIcon className="h-4 w-4" /> {u.whatsapp}</a>}
                  {u.nationality && <span className="flex items-center gap-1.5 capitalize"><Globe className="h-3.5 w-3.5" /> {u.nationality}</span>}
                  {(u.city || u.country) && <span className="flex items-center gap-1.5"><MapPin className="h-3.5 w-3.5" /> {[u.city, u.country].filter(Boolean).join(", ")}</span>}
                </div>
                {u.role !== "admin" && (onChat || onCall) && (
                  <div className="flex flex-wrap gap-2 mt-3">
                    {onChat && <Button size="sm" variant="outline" className="rounded-full" onClick={() => onChat(u)} data-testid="profile-chat-btn"><MessageSquare className="h-4 w-4 mr-1.5" /> Discuter</Button>}
                    {onCall && <Button size="sm" variant="outline" className="rounded-full" onClick={() => onCall(u, "audio")} data-testid="profile-audio-btn"><Phone className="h-4 w-4 mr-1.5" /> Appel audio</Button>}
                    {onCall && <Button size="sm" className="rounded-full" onClick={() => onCall(u, "video")} data-testid="profile-video-btn"><Video className="h-4 w-4 mr-1.5" /> Appel vidéo</Button>}
                  </div>
                )}
              </div>
            </div>

            {/* CV */}
            {u.cv_file_id && (
              <div className="rounded-2xl border border-border bg-card p-5 flex items-center justify-between gap-3" data-testid="profile-cv-card">
                <div className="flex items-center gap-3 min-w-0">
                  <div className="h-10 w-10 rounded-xl bg-primary/10 text-primary flex items-center justify-center shrink-0"><FileText className="h-5 w-5" /></div>
                  <div className="min-w-0">
                    <p className="font-medium text-sm">CV du candidat</p>
                    <p className="text-xs text-muted-foreground truncate">{u.cv_filename || "Document"}</p>
                  </div>
                </div>
                <Button asChild size="sm" variant="outline" className="rounded-full shrink-0" data-testid="profile-cv-btn">
                  <a href={fileUrl(u.cv_file_id)} target="_blank" rel="noreferrer"><FileText className="h-4 w-4 mr-1.5" /> Voir le CV</a>
                </Button>
              </div>
            )}

            {/* Stats */}
            <div className="grid grid-cols-4 gap-3">
              {[
                { label: "Candidatures", value: apps.length, Icon: FileText },
                { label: "Entretiens", value: interviews.length, Icon: CalendarDays },
                { label: "Contrats", value: contracts.length, Icon: ScrollText },
                { label: "Années d'exp.", value: u.years_experience ?? "—", Icon: Briefcase },
              ].map((s) => (
                <div key={s.label} className="rounded-xl border border-border bg-card p-3 text-center">
                  <s.Icon className="h-4 w-4 text-primary mx-auto mb-1.5" />
                  <p className="font-display text-xl font-semibold leading-none">{s.value}</p>
                  <p className="text-[11px] text-muted-foreground mt-1">{s.label}</p>
                </div>
              ))}
            </div>

            {/* Expertise */}
            <div className="rounded-2xl border border-border bg-card p-5 space-y-4">
              <p className="font-medium">Expertise</p>
              <div>
                <p className="text-xs font-semibold text-muted-foreground mb-1.5">Domaines</p>
                <Chips items={u.domains} variant="primary" />
              </div>
              <div>
                <p className="text-xs font-semibold text-muted-foreground mb-1.5">Outils maîtrisés</p>
                <Chips items={u.tools} />
              </div>
              {u.ai_domains?.length > 0 && (
                <div className="flex items-start gap-2 rounded-lg bg-primary/5 border border-primary/20 p-3 text-sm">
                  <Sparkles className="h-4 w-4 text-primary shrink-0 mt-0.5" />
                  <span>Domaines détectés par l'IA : <b>{u.ai_domains.join(", ")}</b></span>
                </div>
              )}
            </div>

            {/* Bio */}
            {u.bio && (
              <div className="rounded-2xl border border-border bg-card p-5">
                <p className="font-medium mb-2">À propos</p>
                <p className="text-sm text-muted-foreground whitespace-pre-wrap">{u.bio}</p>
              </div>
            )}

            {/* Applications */}
            <div className="rounded-2xl border border-border bg-card p-5">
              <div className="flex items-center justify-between mb-3 gap-2 flex-wrap">
                <p className="font-medium">Candidatures ({apps.length})</p>
                <Button size="sm" variant="outline" className="rounded-full" onClick={() => setAddOpen((o) => !o)} data-testid="add-application-btn">+ Ajouter une candidature</Button>
              </div>
              {addOpen && (
                <div className="rounded-xl border border-border p-3 mb-3 space-y-2" data-testid="add-application-form">
                  <select value={njob} onChange={(e) => setNjob(e.target.value)} data-testid="add-app-job" className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm">
                    <option value="">— Choisir une offre —</option>
                    {jobs.map((j) => <option key={j.id} value={j.id}>{j.title}</option>)}
                  </select>
                  <select value={nstatus} onChange={(e) => setNstatus(e.target.value)} data-testid="add-app-status" className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm">
                    <option value="interview_scheduled">Entretien fixé</option>
                    <option value="interview_done">Entretien fait</option>
                    <option value="pending">En attente</option>
                    <option value="accepted">Acceptée</option>
                    <option value="rejected">Refusée</option>
                  </select>
                  <Button size="sm" className="rounded-full w-full" onClick={addApplication} disabled={adding} data-testid="add-app-submit">{adding ? "Création…" : "Créer la candidature"}</Button>
                </div>
              )}
              {apps.length === 0 ? (
                <p className="text-sm text-muted-foreground">Aucune candidature.</p>
              ) : (
                <div className="space-y-3">
                  {apps.map((a) => (
                    <div key={a.id} className="rounded-xl border border-border p-3" data-testid={`profile-app-${a.id}`}>
                      <div className="flex items-center justify-between gap-3 flex-wrap">
                        <div>
                          <p className="font-medium text-sm">{a.job_title}</p>
                          <p className="text-xs text-muted-foreground">Postulé le {fmtDate(a.created_at)}</p>
                        </div>
                        <div className="flex items-center gap-2">
                          {a.rating > 0 && (
                            <span className="flex items-center gap-0.5 text-primary text-xs font-semibold">
                              <Star className="h-3.5 w-3.5 fill-primary" /> {a.rating}/5
                            </span>
                          )}
                          <StatusBadge status={a.status} />
                        </div>
                      </div>
                      {a.admin_note && <p className="text-xs text-muted-foreground italic mt-2">Note interne : {a.admin_note}</p>}
                      {a.interview_note && <p className="text-xs text-purple-600 italic mt-2" data-testid={`app-iv-note-${a.id}`}>Note d'entretien : {a.interview_note}</p>}
                      <div className="flex gap-2 mt-2">
                        {a.cv_file_id && (
                          <a href={fileUrl(a.cv_file_id)} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs text-primary hover:underline">
                            <FileText className="h-3.5 w-3.5" /> CV
                          </a>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Interviews */}
            {interviews.length > 0 && (
              <div className="rounded-2xl border border-border bg-card p-5">
                <p className="font-medium mb-3">Entretiens ({interviews.length})</p>
                <div className="space-y-2">
                  {interviews.map((i) => (
                    <div key={i.id} className="flex items-center gap-3 text-sm">
                      <Clock className="h-4 w-4 text-primary" />
                      <span className="font-medium">{i.title}</span>
                      <span className="text-muted-foreground">{fmtDate(i.date)} à {i.time}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

