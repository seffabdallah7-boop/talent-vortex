import { useEffect, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import api, { formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import Navbar from "@/components/Navbar";
import ChatWidget from "@/components/ChatWidget";
import VoiceRecorder from "@/components/VoiceRecorder";
import StatusBadge from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { MapPin, Briefcase, Clock, Upload, Loader2, FileText, ArrowLeft, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";

export default function JobDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [job, setJob] = useState(null);
  const [cv, setCv] = useState(null);
  const [voice, setVoice] = useState(null);
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [myApp, setMyApp] = useState(null);
  const [profile, setProfile] = useState(null);

  useEffect(() => {
    api.get(`/jobs/${id}`).then(({ data }) => setJob(data)).catch(() => navigate("/"));
  }, [id, navigate]);

  useEffect(() => {
    if (user && user.role !== "admin") {
      api.get("/applications/me")
        .then(({ data }) => setMyApp((data || []).find((a) => a.job_id === id) || null))
        .catch(() => {});
      api.get("/profile").then(({ data }) => setProfile(data)).catch(() => {});
    } else {
      setMyApp(null);
    }
  }, [id, user, done]);

  const submit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    const fd = new FormData();
    fd.append("job_id", id);
    fd.append("cover_note", note);
    fd.append("salary_expectation", e.target.salary_expectation?.value || "");
    if (cv) fd.append("cv", cv);
    if (voice) fd.append("voice", voice, "message-vocal.webm");
    try {
      const { data } = await api.post("/applications", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success("Candidature envoyée !");
      if (data?.screening?.questions?.length) {
        navigate("/dashboard?section=applications");
        return;
      }
      setDone(true);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail) || "Erreur lors de l'envoi");
    } finally {
      setSubmitting(false);
    }
  };

  if (!job) return <div className="min-h-screen flex items-center justify-center"><Loader2 className="h-8 w-8 animate-spin text-primary" /></div>;

  return (
    <div className="App">
      <Navbar />
      <div className="max-w-5xl mx-auto px-5 py-10">
        <Link to="/" className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-6" data-testid="back-link">
          <ArrowLeft className="h-4 w-4" /> Retour aux offres
        </Link>

        <div className="rounded-2xl border border-border bg-card p-8 mb-8">
          <div className="flex items-center gap-2 mb-4">
            <span className="text-xs font-semibold rounded-full bg-secondary px-3 py-1">{job.category}</span>
            <span className="text-xs text-muted-foreground">{job.type}</span>
          </div>
          <h1 className="font-display text-3xl lg:text-4xl font-semibold mb-2" data-testid="job-title">{job.title}</h1>
          <p className="text-lg font-medium text-muted-foreground mb-4">{job.company}</p>
          <div className="flex flex-wrap items-center gap-5 text-sm text-muted-foreground">
            <span className="flex items-center gap-1.5"><MapPin className="h-4 w-4" /> {job.location}</span>
            {job.salary && <span className="flex items-center gap-1.5"><Briefcase className="h-4 w-4" /> {job.salary}</span>}
            <span className="flex items-center gap-1.5"><Clock className="h-4 w-4" /> {job.type}</span>
          </div>
          <div className="prose prose-sm max-w-none mt-6">
            <h3 className="font-display text-lg font-semibold">Description du poste</h3>
            <p className="text-muted-foreground whitespace-pre-wrap">{job.description}</p>
            {job.requirements && (
              <>
                <h3 className="font-display text-lg font-semibold mt-4">Profil recherché</h3>
                <p className="text-muted-foreground whitespace-pre-wrap">{job.requirements}</p>
              </>
            )}
          </div>
        </div>

        <div className="rounded-2xl border border-border bg-card p-8" id="postuler">
          <h2 className="font-display text-2xl font-semibold mb-6">Postuler à cette offre</h2>

          {done ? (
            <div className="text-center py-8" data-testid="apply-success">
              <CheckCircle2 className="h-14 w-14 text-[hsl(var(--status-accepted))] mx-auto mb-4" />
              <h3 className="font-display text-xl font-semibold mb-2">Candidature envoyée !</h3>
              <p className="text-muted-foreground mb-6">Suivez son statut depuis votre espace candidat.</p>
              <Button onClick={() => navigate("/dashboard")} className="rounded-full" data-testid="goto-dashboard-btn">Voir mes candidatures</Button>
            </div>
          ) : !user ? (
            <div className="text-center py-8">
              <p className="text-muted-foreground mb-4">Connectez-vous pour postuler.</p>
              <Button onClick={() => navigate("/login")} className="rounded-full" data-testid="login-to-apply-btn">Se connecter</Button>
            </div>
          ) : user.role === "admin" ? (
            <p className="text-muted-foreground">Les administrateurs ne peuvent pas postuler.</p>
          ) : myApp ? (
            <div className="rounded-xl border border-border bg-secondary/40 p-6" data-testid="already-applied">
              <div className="flex items-center justify-between gap-4 flex-wrap">
                <div>
                  <p className="font-medium mb-1">Vous avez déjà postulé à cette offre.</p>
                  <p className="text-sm text-muted-foreground">Postulé le {new Date(myApp.created_at).toLocaleDateString("fr-FR")}</p>
                </div>
                <StatusBadge status={myApp.status} />
              </div>
              <Button variant="outline" onClick={() => navigate("/dashboard")} className="rounded-full mt-4" data-testid="view-my-application-btn">Voir ma candidature</Button>
            </div>
          ) : profile && !(profile.phone && profile.domains && profile.domains.length && profile.cv_file_id) ? (
            <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-6" data-testid="profile-incomplete-block">
              <p className="font-medium mb-1">Complétez votre profil pour postuler</p>
              <p className="text-sm text-muted-foreground mb-4">Renseignez votre <strong>téléphone</strong> et vos <strong>domaines d'expertise</strong>, et ajoutez votre <strong>CV</strong> — ces informations sont indispensables à notre matching IA.</p>
              <Button onClick={() => navigate("/dashboard?section=profile")} className="rounded-full" data-testid="complete-profile-cta">Compléter mon profil</Button>
            </div>
          ) : (
            <form onSubmit={submit} className="space-y-6">
              <div>
                <Label className="mb-2 block">CV pour cette candidature <span className="text-muted-foreground font-normal">(facultatif — le CV de votre profil est utilisé par défaut)</span></Label>
                <label className="flex items-center gap-3 rounded-xl border border-dashed border-border p-5 cursor-pointer hover:border-primary transition-colors" data-testid="cv-upload-label">
                  <div className="h-11 w-11 rounded-lg bg-primary/10 flex items-center justify-center">
                    {cv ? <FileText className="h-5 w-5 text-primary" /> : <Upload className="h-5 w-5 text-primary" />}
                  </div>
                  <div className="flex-1">
                    <p className="font-medium text-sm">{cv ? cv.name : "Cliquez pour joindre votre CV"}</p>
                    <p className="text-xs text-muted-foreground">Formats acceptés : PDF, DOC, DOCX</p>
                  </div>
                  <input type="file" accept=".pdf,.doc,.docx" className="hidden" data-testid="cv-input" onChange={(e) => setCv(e.target.files[0])} />
                </label>
              </div>

              <div>
                <Label className="mb-2 block">Message vocal (facultatif, max 10 min)</Label>
                <VoiceRecorder onChange={setVoice} />
              </div>

              <div>
                <Label htmlFor="note" className="mb-2 block">Note de motivation (facultatif)</Label>
                <Textarea id="note" data-testid="cover-note-input" value={note} onChange={(e) => setNote(e.target.value)} rows={4} placeholder="Quelques mots sur votre motivation..." />
              </div>

              <div>
                <Label htmlFor="salary_expectation" className="mb-2 block">Prétention salariale (facultatif)</Label>
                <input id="salary_expectation" name="salary_expectation" data-testid="salary-expectation-input" placeholder="Ex : 45 000 € / an, ou à négocier" className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring" />
              </div>

              <Button type="submit" disabled={submitting} className="rounded-full h-12 px-8" data-testid="submit-application-btn">
                {submitting ? <><Loader2 className="h-4 w-4 animate-spin mr-2" /> Envoi en cours...</> : "Envoyer ma candidature"}
              </Button>
            </form>
          )}
        </div>
      </div>
      <ChatWidget />
          </div>
  );
}
