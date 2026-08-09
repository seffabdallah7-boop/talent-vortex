import { useEffect, useState, useCallback, useRef } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import api, { fileUrl, formatApiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import Navbar from "@/components/Navbar";
import ChatWidget from "@/components/ChatWidget";
import StatusBadge from "@/components/StatusBadge";
import VideoCall from "@/components/VideoCall";
import AudioPlayer from "@/components/AudioPlayer";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import {
  FileText, Plus, Briefcase, Clock, CheckCircle2, XCircle, CalendarDays, Video,
  ScrollText, User, Loader2, Sparkles,
} from "lucide-react";
import { toast } from "sonner";

const STEPS = [
  { key: "pending", label: "Reçue / En attente", Icon: Clock },
  { key: "accepted", label: "Acceptée", Icon: CheckCircle2 },
];

const fmtDate = (d) => { try { return new Date(d + "T00:00:00").toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" }); } catch { return d; } };

export default function CandidateDashboard() {
  const { user, checkAuth } = useAuth();
  const [apps, setApps] = useState([]);
  const [interviews, setInterviews] = useState([]);
  const [contracts, setContracts] = useState([]);
  const [notifs, setNotifs] = useState([]);
  const [profile, setProfile] = useState(null);
  const [section, setSection] = useState("applications");
  const [call, setCall] = useState(null);
  const [reminder, setReminder] = useState(null);
  const didAutoNav = useRef(false);
  const alerted = useRef(new Set());

  const loadAll = useCallback(() => {
    api.get("/applications/me").then(({ data }) => setApps(data)).catch(() => {});
    api.get("/interviews/me").then(({ data }) => setInterviews(data)).catch(() => {});
    api.get("/contracts/me").then(({ data }) => setContracts(data)).catch(() => {});
    api.get("/notifications").then(({ data }) => setNotifs(data.items || [])).catch(() => {});
    api.get("/profile").then(({ data }) => {
      setProfile(data);
      if (!data.profile_completed && !didAutoNav.current) { setSection("profile"); didAutoNav.current = true; }
    }).catch(() => {});
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  useEffect(() => {
    const check = () => {
      const now = Date.now();
      for (const i of interviews) {
        if (!i.date || !i.time) continue;
        const start = new Date(`${i.date}T${i.time}`).getTime();
        const diff = start - now;
        if (diff > 0 && diff <= 5 * 60 * 1000) {
          setReminder(i);
          if (!alerted.current.has(i.id)) {
            alerted.current.add(i.id);
            toast.info(`Votre entretien « ${i.title} » commence dans ${Math.ceil(diff / 60000)} min`, { duration: 10000 });
          }
          return;
        }
      }
      setReminder(null);
    };
    check();
    const t = setInterval(check, 30000);
    return () => clearInterval(t);
  }, [interviews]);

  const unreadByType = (t) => notifs.filter((n) => !n.read && n.type === t).length;

  const NAV = [
    { key: "applications", label: "Mes postulations", Icon: FileText, badge: unreadByType("status"), count: apps.length },
    { key: "interviews", label: "Mes entretiens", Icon: CalendarDays, badge: unreadByType("interview"), count: interviews.length },
    { key: "contracts", label: "Contrats obtenus", Icon: ScrollText, count: contracts.length },
    { key: "profile", label: "Mon profil", Icon: User, badge: profile && !profile.profile_completed ? "!" : 0 },
  ];

  return (
    <div className="App">
      <Navbar />
      {call && <VideoCall room={call.room} audioOnly={call.audioOnly} title="Entretien" onClose={() => setCall(null)} />}
      <div className="max-w-7xl mx-auto px-5 py-8 grid lg:grid-cols-[260px_1fr] gap-8">
        {/* Sidebar */}
        <aside className="lg:sticky lg:top-24 h-fit" data-testid="candidate-sidebar">
          <div className="mb-6">
            <p className="label-caps text-primary mb-1">Espace candidat</p>
            <h1 className="font-display text-2xl font-semibold leading-tight">{user?.name}</h1>
          </div>
          <nav className="space-y-1.5">
            {NAV.map((n) => (
              <button
                key={n.key}
                onClick={() => setSection(n.key)}
                data-testid={`sidebar-${n.key}`}
                className={`w-full flex items-center gap-3 rounded-xl px-4 py-2.5 text-sm font-medium transition-colors ${section === n.key ? "bg-primary text-primary-foreground" : "hover:bg-secondary text-muted-foreground hover:text-foreground"}`}
              >
                <n.Icon className="h-4 w-4" />
                <span className="flex-1 text-left">{n.label}</span>
                {typeof n.count === "number" && n.count > 0 && (
                  <span className={`text-xs ${section === n.key ? "text-primary-foreground/80" : "text-muted-foreground"}`}>{n.count}</span>
                )}
                {n.badge ? (
                  <span data-testid={`sidebar-badge-${n.key}`} className="h-5 min-w-5 px-1 rounded-full bg-destructive text-white text-[10px] font-bold flex items-center justify-center">{n.badge}</span>
                ) : null}
              </button>
            ))}
          </nav>
          <Button asChild className="rounded-full w-full mt-6" data-testid="browse-jobs-btn">
            <Link to="/"><Plus className="h-4 w-4 mr-2" /> Nouvelle candidature</Link>
          </Button>
        </aside>

        {/* Content */}
        <main className="min-w-0">
          {reminder && (
            <div className="rounded-2xl border border-primary bg-primary/10 p-4 mb-6 flex items-center justify-between gap-3" data-testid="interview-reminder-banner">
              <div className="flex items-center gap-3">
                <CalendarDays className="h-5 w-5 text-primary shrink-0" />
                <div>
                  <p className="font-medium">Entretien imminent : {reminder.title}</p>
                  <p className="text-sm text-muted-foreground">Aujourd'hui à {reminder.time}</p>
                </div>
              </div>
              <Button size="sm" className="rounded-full" onClick={() => setCall({ room: `recrutai-itw-${reminder.id}`, audioOnly: false })} data-testid="reminder-join-btn"><Video className="h-4 w-4 mr-1.5" /> Rejoindre</Button>
            </div>
          )}
          {profile && !profile.profile_completed && (
            <div className="rounded-2xl border border-primary/30 bg-primary/5 p-5 mb-6 flex items-start gap-3" data-testid="profile-incomplete-banner">
              <Sparkles className="h-5 w-5 text-primary shrink-0 mt-0.5" />
              <div className="flex-1">
                <p className="font-medium">Complétez votre profil</p>
                <p className="text-sm text-muted-foreground">Renseignez vos infos et domaines d'expertise : l'IA vous proposera en priorité les offres de votre domaine.</p>
              </div>
              <Button size="sm" className="rounded-full" onClick={() => setSection("profile")} data-testid="complete-profile-btn">Compléter</Button>
            </div>
          )}

          {section === "applications" && <Applications apps={apps} />}
          {section === "interviews" && <InterviewsView interviews={interviews} onJoin={(i) => setCall({ room: `recrutai-itw-${i.id}`, audioOnly: false })} />}
          {section === "contracts" && <ContractsView contracts={contracts} />}
          {section === "profile" && <ProfileForm profile={profile} onSaved={() => { loadAll(); checkAuth(); }} />}
        </main>
      </div>
      <ChatWidget />
    </div>
  );
}

function Applications({ apps }) {
  if (apps.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border p-16 text-center" data-testid="no-applications">
        <Briefcase className="h-12 w-12 text-muted-foreground/40 mx-auto mb-4" />
        <p className="text-muted-foreground mb-5">Vous n'avez pas encore postulé.</p>
        <Button asChild className="rounded-full"><Link to="/">Parcourir les offres</Link></Button>
      </div>
    );
  }
  return (
    <div className="space-y-5">
      <h2 className="font-display text-2xl font-semibold">Mes postulations</h2>
      {apps.map((a, i) => (
        <motion.div key={a.id} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.05 }} className="rounded-2xl border border-border bg-card p-6" data-testid={`application-${a.id}`}>
          <div className="flex flex-wrap items-start justify-between gap-4 mb-4">
            <div>
              <h3 className="font-display text-xl font-semibold">{a.job_title}</h3>
              <p className="text-sm text-muted-foreground">Postulé le {new Date(a.created_at).toLocaleDateString("fr-FR")}</p>
            </div>
            <StatusBadge status={a.status} />
          </div>
          <div className="flex items-center gap-2 mb-5">
            {a.status === "rejected" ? (
              <div className="flex items-center gap-2 text-sm text-[hsl(var(--status-rejected))]"><XCircle className="h-5 w-5" /> Candidature non retenue</div>
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
          <div className="flex flex-col gap-3">
            {a.voice_file_id && <AudioPlayer src={fileUrl(a.voice_file_id)} testId={`voice-player-${a.id}`} />}
            {a.cv_file_id && (
              <Button asChild variant="outline" size="sm" className="rounded-full w-fit" data-testid={`view-cv-${a.id}`}>
                <a href={fileUrl(a.cv_file_id)} target="_blank" rel="noreferrer"><FileText className="h-4 w-4 mr-2" /> Mon CV</a>
              </Button>
            )}
          </div>
        </motion.div>
      ))}
    </div>
  );
}

function InterviewsView({ interviews, onJoin }) {
  if (interviews.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border p-16 text-center text-muted-foreground" data-testid="no-interviews">
        <CalendarDays className="h-12 w-12 text-muted-foreground/40 mx-auto mb-4" />
        Aucun entretien planifié pour le moment.
      </div>
    );
  }
  return (
    <div className="space-y-4" data-testid="candidate-interviews">
      <h2 className="font-display text-2xl font-semibold">Mes entretiens</h2>
      {interviews.map((i) => (
        <div key={i.id} className="rounded-2xl border border-border bg-card p-5 flex flex-wrap items-center justify-between gap-4" data-testid={`candidate-interview-${i.id}`}>
          <div className="flex items-center gap-4">
            <div className="h-12 w-12 rounded-xl bg-primary/10 text-primary flex items-center justify-center">
              <span className="font-mono text-sm font-bold">{i.time}</span>
            </div>
            <div>
              <p className="font-medium">{i.title}</p>
              <p className="text-xs text-muted-foreground capitalize">{fmtDate(i.date)}{i.location ? ` • ${i.location}` : ""}</p>
            </div>
          </div>
          <Button size="sm" className="rounded-full" onClick={() => onJoin(i)} data-testid={`candidate-join-interview-${i.id}`}>
            <Video className="h-4 w-4 mr-1.5" /> Rejoindre
          </Button>
        </div>
      ))}
    </div>
  );
}

function ContractsView({ contracts }) {
  const LABELS = { en_cours: "En cours", boucle: "Bouclé", resilie: "Résilié" };
  if (contracts.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-border p-16 text-center text-muted-foreground" data-testid="no-contracts">
        <ScrollText className="h-12 w-12 text-muted-foreground/40 mx-auto mb-4" />
        Aucun contrat pour le moment.
      </div>
    );
  }
  return (
    <div className="space-y-4" data-testid="candidate-contracts">
      <h2 className="font-display text-2xl font-semibold">Contrats obtenus</h2>
      {contracts.map((c) => (
        <div key={c.id} className="rounded-2xl border border-border bg-card p-5" data-testid={`contract-${c.id}`}>
          <div className="flex items-start justify-between gap-4 mb-2">
            <div>
              <h3 className="font-display text-lg font-semibold">{c.title}</h3>
              <p className="text-sm text-muted-foreground">{[c.client, c.job_title].filter(Boolean).join(" • ")}</p>
            </div>
            <span className="rounded-full bg-primary/10 text-primary px-3 py-1 text-xs font-semibold">{LABELS[c.status] || c.status}</span>
          </div>
          <div className="flex flex-wrap gap-4 text-sm text-muted-foreground mt-2">
            {c.amount && <span>💰 {c.amount}</span>}
            {c.start_date && <span>Du {c.start_date}</span>}
            {c.end_date && <span>au {c.end_date}</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

function ProfileForm({ profile, onSaved }) {
  const [form, setForm] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (profile) {
      setForm({
        name: profile.name || "",
        phone: profile.phone || "",
        nationality: profile.nationality || "",
        city: profile.city || "",
        country: profile.country || "",
        current_position: profile.current_position || "",
        years_experience: profile.years_experience ?? "",
        headline: profile.headline || "",
        bio: profile.bio || "",
        domains: (profile.domains || []).join(", "),
        tools: (profile.tools || []).join(", "),
      });
    }
  }, [profile]);

  if (!form) return <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>;

  const save = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.put("/profile", {
        name: form.name,
        phone: form.phone,
        nationality: form.nationality,
        city: form.city,
        country: form.country,
        current_position: form.current_position,
        years_experience: form.years_experience === "" ? null : Number(form.years_experience),
        headline: form.headline,
        bio: form.bio,
        domains: form.domains.split(",").map((s) => s.trim()).filter(Boolean),
        tools: form.tools.split(",").map((s) => s.trim()).filter(Boolean),
      });
      toast.success("Profil enregistré. L'IA affinera vos recommandations d'offres.");
      onSaved?.();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail) || "Erreur");
    } finally {
      setSaving(false);
    }
  };

  const field = (k) => ({ value: form[k], onChange: (e) => setForm({ ...form, [k]: e.target.value }) });

  return (
    <form onSubmit={save} className="space-y-6" data-testid="profile-form">
      <div>
        <h2 className="font-display text-2xl font-semibold">Mon profil</h2>
        <p className="text-sm text-muted-foreground">Ces informations aident notre IA à vous proposer les offres les plus pertinentes.</p>
      </div>

      <div className="rounded-2xl border border-border bg-card p-6 space-y-4">
        <p className="font-medium">Informations personnelles</p>
        <div className="grid sm:grid-cols-2 gap-4">
          <div><Label>Nom complet *</Label><Input className="mt-1.5" data-testid="profile-name" {...field("name")} required /></div>
          <div><Label>Téléphone *</Label><Input className="mt-1.5" data-testid="profile-phone" {...field("phone")} required /></div>
          <div><Label>Nationalité *</Label><Input className="mt-1.5" data-testid="profile-nationality" placeholder="Ex : Française" {...field("nationality")} required /></div>
          <div><Label>Ville</Label><Input className="mt-1.5" data-testid="profile-city" {...field("city")} /></div>
          <div><Label>Pays</Label><Input className="mt-1.5" data-testid="profile-country" {...field("country")} /></div>
          <div><Label>Années d'expérience</Label><Input type="number" min="0" className="mt-1.5" data-testid="profile-years" {...field("years_experience")} /></div>
        </div>
      </div>

      <div className="rounded-2xl border border-border bg-card p-6 space-y-4">
        <p className="font-medium">Expertise</p>
        <div><Label>Poste actuel</Label><Input className="mt-1.5" data-testid="profile-position" placeholder="Ex : Développeur Full-Stack" {...field("current_position")} /></div>
        <div><Label>Domaines d'expertise * <span className="text-muted-foreground font-normal">(séparés par des virgules)</span></Label><Input className="mt-1.5" data-testid="profile-domains" placeholder="Ex : Tech, Data" {...field("domains")} /></div>
        <div><Label>Outils maîtrisés <span className="text-muted-foreground font-normal">(séparés par des virgules)</span></Label><Input className="mt-1.5" data-testid="profile-tools" placeholder="Ex : React, Python, Figma" {...field("tools")} /></div>
        <div><Label>Titre / accroche</Label><Input className="mt-1.5" data-testid="profile-headline" placeholder="Ex : Ingénieur logiciel passionné" {...field("headline")} /></div>
        <div><Label>À propos</Label><Textarea rows={4} className="mt-1.5" data-testid="profile-bio" placeholder="Parlez de votre parcours..." {...field("bio")} /></div>
      </div>

      {profile.ai_domains?.length > 0 && (
        <div className="rounded-xl bg-primary/5 border border-primary/20 p-4 flex items-center gap-2 text-sm" data-testid="ai-domains">
          <Sparkles className="h-4 w-4 text-primary" />
          <span>Domaines détectés par l'IA : <b>{profile.ai_domains.join(", ")}</b></span>
        </div>
      )}

      <Button type="submit" disabled={saving} className="rounded-full h-11 px-8" data-testid="save-profile-btn">
        {saving ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null} Enregistrer mon profil
      </Button>
    </form>
  );
}
