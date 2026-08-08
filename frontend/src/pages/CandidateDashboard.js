import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import api, { fileUrl } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import Navbar from "@/components/Navbar";
import ChatWidget from "@/components/ChatWidget";
import VideoCall from "@/components/VideoCall";
import StatusBadge from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { FileText, Volume2, Plus, Briefcase, Clock, CheckCircle2, XCircle, CalendarDays, Video } from "lucide-react";

const STEPS = [
  { key: "pending", label: "Reçue / En attente", Icon: Clock },
  { key: "accepted", label: "Acceptée", Icon: CheckCircle2 },
];

export default function CandidateDashboard() {
  const { user } = useAuth();
  const [apps, setApps] = useState([]);
  const [interviews, setInterviews] = useState([]);
  const [call, setCall] = useState(null);

  useEffect(() => {
    api.get("/applications/me").then(({ data }) => setApps(data)).catch(() => {});
    api.get("/interviews/me").then(({ data }) => setInterviews(data)).catch(() => {});
  }, []);

  const fmtDate = (d) => { try { return new Date(d + "T00:00:00").toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" }); } catch { return d; } };

  return (
    <div className="App">
      <Navbar />
      {call && <VideoCall room={call.room} audioOnly={call.audioOnly} title="Entretien" onClose={() => setCall(null)} />}
      <div className="max-w-6xl mx-auto px-5 py-10">
        <div className="flex items-center justify-between mb-8">
          <div>
            <p className="label-caps text-primary mb-1">Espace candidat</p>
            <h1 className="font-display text-3xl font-semibold">Bonjour, {user?.name}</h1>
          </div>
          <Button asChild className="rounded-full" data-testid="browse-jobs-btn">
            <Link to="/"><Plus className="h-4 w-4 mr-2" /> Nouvelle candidature</Link>
          </Button>
        </div>

        {interviews.length > 0 && (
          <div className="mb-10" data-testid="candidate-interviews">
            <h2 className="font-display text-xl font-semibold mb-4 flex items-center gap-2"><CalendarDays className="h-5 w-5 text-primary" /> Mes entretiens</h2>
            <div className="space-y-3">
              {interviews.map((i) => (
                <div key={i.id} className="rounded-2xl border border-border bg-card p-5 flex flex-wrap items-center justify-between gap-4" data-testid={`candidate-interview-${i.id}`}>
                  <div className="flex items-center gap-4">
                    <div className="h-12 w-12 rounded-xl bg-primary/10 text-primary flex flex-col items-center justify-center leading-none">
                      <span className="font-mono text-sm font-bold">{i.time}</span>
                    </div>
                    <div>
                      <p className="font-medium">{i.title}</p>
                      <p className="text-xs text-muted-foreground capitalize">{fmtDate(i.date)}{i.location ? ` • ${i.location}` : ""}</p>
                    </div>
                  </div>
                  <Button size="sm" className="rounded-full" onClick={() => setCall({ room: `recrutai-itw-${i.id}`, audioOnly: false })} data-testid={`candidate-join-interview-${i.id}`}>
                    <Video className="h-4 w-4 mr-1.5" /> Rejoindre
                  </Button>
                </div>
              ))}
            </div>
          </div>
        )}

        {apps.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-border p-16 text-center" data-testid="no-applications">
            <Briefcase className="h-12 w-12 text-muted-foreground/40 mx-auto mb-4" />
            <p className="text-muted-foreground mb-5">Vous n'avez pas encore postulé.</p>
            <Button asChild className="rounded-full"><Link to="/">Parcourir les offres</Link></Button>
          </div>
        ) : (
          <div className="space-y-5">
            {apps.map((a, i) => (
              <motion.div
                key={a.id}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05 }}
                className="rounded-2xl border border-border bg-card p-6"
                data-testid={`application-${a.id}`}
              >
                <div className="flex flex-wrap items-start justify-between gap-4 mb-4">
                  <div>
                    <h3 className="font-display text-xl font-semibold">{a.job_title}</h3>
                    <p className="text-sm text-muted-foreground">Postulé le {new Date(a.created_at).toLocaleDateString("fr-FR")}</p>
                  </div>
                  <StatusBadge status={a.status} />
                </div>

                {/* Status timeline */}
                <div className="flex items-center gap-2 mb-5">
                  {a.status === "rejected" ? (
                    <div className="flex items-center gap-2 text-sm text-[hsl(var(--status-rejected))]">
                      <XCircle className="h-5 w-5" /> Candidature non retenue
                    </div>
                  ) : (
                    STEPS.map((s, idx) => {
                      const active = s.key === "pending" || a.status === "accepted";
                      const isCurrent = (a.status === "pending" && s.key === "pending") || (a.status === "accepted" && s.key === "accepted");
                      return (
                        <div key={s.key} className="flex items-center gap-2">
                          <div className={`flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-medium ${active ? "bg-primary/10 text-primary" : "bg-secondary text-muted-foreground"} ${isCurrent ? "ring-2 ring-primary/30" : ""}`}>
                            <s.Icon className="h-3.5 w-3.5" /> {s.label}
                          </div>
                          {idx < STEPS.length - 1 && <div className={`h-0.5 w-8 ${a.status === "accepted" ? "bg-primary" : "bg-border"}`} />}
                        </div>
                      );
                    })
                  )}
                </div>

                {a.cover_note && <p className="text-sm text-muted-foreground mb-4 italic">"{a.cover_note}"</p>}
                {a.transcription && (
                  <div className="rounded-lg bg-secondary/50 p-3 mb-4">
                    <p className="text-xs font-semibold text-muted-foreground mb-1">Transcription de votre message vocal</p>
                    <p className="text-sm">{a.transcription}</p>
                  </div>
                )}

                <div className="flex flex-wrap gap-3">
                  {a.cv_file_id && (
                    <Button asChild variant="outline" size="sm" className="rounded-full" data-testid={`view-cv-${a.id}`}>
                      <a href={fileUrl(a.cv_file_id)} target="_blank" rel="noreferrer"><FileText className="h-4 w-4 mr-2" /> Mon CV</a>
                    </Button>
                  )}
                  {a.voice_file_id && (
                    <Button asChild variant="outline" size="sm" className="rounded-full" data-testid={`play-voice-${a.id}`}>
                      <a href={fileUrl(a.voice_file_id)} target="_blank" rel="noreferrer"><Volume2 className="h-4 w-4 mr-2" /> Mon message vocal</a>
                    </Button>
                  )}
                </div>
              </motion.div>
            ))}
          </div>
        )}
      </div>
      <ChatWidget />
    </div>
  );
}
