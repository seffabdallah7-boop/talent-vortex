import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import api from "@/lib/api";
import Navbar from "@/components/Navbar";
import ChatWidget from "@/components/ChatWidget";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MapPin, Briefcase, Search, ArrowRight, FileAudio, ShieldCheck, Bot } from "lucide-react";

const HERO = "https://images.unsplash.com/photo-1716703373229-b0e43de7dd5c?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMzJ8MHwxfHNlYXJjaHwxfHxtb2Rlcm4lMjBvZmZpY2UlMjBzcGFjZSUyMGludGVyaW9yfGVufDB8fHx8MTc4NjIxNjU3OHww&ixlib=rb-4.1.0&q=85";

export default function Landing() {
  const [jobs, setJobs] = useState([]);
  const [q, setQ] = useState("");

  useEffect(() => {
    api.get("/jobs").then(({ data }) => setJobs(data)).catch(() => {});
  }, []);

  const filtered = jobs.filter(
    (j) =>
      j.title.toLowerCase().includes(q.toLowerCase()) ||
      j.company.toLowerCase().includes(q.toLowerCase()) ||
      j.location.toLowerCase().includes(q.toLowerCase())
  );

  return (
    <div className="App">
      <Navbar />

      <section className="relative overflow-hidden grain">
        <div className="absolute inset-0">
          <img src={HERO} alt="" className="w-full h-full object-cover" />
          <div className="absolute inset-0 bg-black/55" />
        </div>
        <div className="relative max-w-7xl mx-auto px-5 py-24 md:py-32">
          <motion.p initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="label-caps text-white/70 mb-4">
            Recrutement nouvelle génération
          </motion.p>
          <motion.h1
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 }}
            className="font-display text-4xl sm:text-5xl lg:text-6xl font-semibold text-white max-w-3xl leading-[1.05]"
          >
            Trouvez votre prochain emploi. Postulez avec votre voix.
          </motion.h1>
          <motion.p
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.12 }}
            className="text-lg text-white/80 max-w-xl mt-6"
          >
            Déposez votre CV, enregistrez un message vocal de motivation et suivez le statut de vos candidatures en temps réel.
          </motion.p>
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.18 }}
            className="mt-8 flex flex-col sm:flex-row gap-3 max-w-lg"
          >
            <div className="relative flex-1">
              <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
              <Input
                data-testid="job-search-input"
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Poste, entreprise, ville..."
                className="pl-12 h-13 rounded-full bg-white border-0 h-12"
              />
            </div>
            <Button asChild className="rounded-full h-12 px-8" data-testid="hero-cta">
              <a href="#offres">Voir les offres <ArrowRight className="h-4 w-4 ml-2" /></a>
            </Button>
          </motion.div>
        </div>
      </section>

      <section className="max-w-7xl mx-auto px-5 py-16 grid md:grid-cols-3 gap-5">
        {[
          { Icon: FileAudio, t: "CV + Message vocal", d: "Joignez votre CV et un message vocal jusqu'à 10 minutes pour vous démarquer." },
          { Icon: ShieldCheck, t: "Suivi transparent", d: "Visualisez à tout moment le statut : en attente, acceptée ou refusée." },
          { Icon: Bot, t: "Assistant IA 24/7", d: "Un assistant intelligent répond à toutes vos questions instantanément." },
        ].map((f, i) => (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.08 }}
            className="rounded-2xl border border-border bg-card p-8 hover:-translate-y-1 hover:shadow-lg transition-transform"
          >
            <div className="h-12 w-12 rounded-xl bg-primary/10 flex items-center justify-center mb-5">
              <f.Icon className="h-6 w-6 text-primary" />
            </div>
            <h3 className="font-display text-xl font-semibold mb-2">{f.t}</h3>
            <p className="text-muted-foreground leading-relaxed">{f.d}</p>
          </motion.div>
        ))}
      </section>

      <section id="offres" className="max-w-7xl mx-auto px-5 pb-24">
        <div className="flex items-end justify-between mb-8">
          <div>
            <p className="label-caps text-primary mb-2">Offres d'emploi</p>
            <h2 className="font-display text-3xl lg:text-4xl font-semibold">{filtered.length} poste{filtered.length > 1 ? "s" : ""} disponible{filtered.length > 1 ? "s" : ""}</h2>
          </div>
        </div>

        {filtered.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-border p-16 text-center text-muted-foreground" data-testid="no-jobs">
            Aucune offre pour le moment. Revenez bientôt !
          </div>
        ) : (
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-5">
            {filtered.map((job, i) => (
              <motion.div
                key={job.id}
                initial={{ opacity: 0, y: 16 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: (i % 3) * 0.06 }}
              >
                <Link
                  to={`/jobs/${job.id}`}
                  data-testid={`job-card-${job.id}`}
                  className="group block h-full rounded-2xl border border-border bg-card p-6 hover:-translate-y-1 hover:shadow-lg transition-transform"
                >
                  <div className="flex items-center gap-2 mb-4">
                    <span className="text-xs font-semibold rounded-full bg-secondary px-3 py-1">{job.category}</span>
                    <span className="text-xs text-muted-foreground">{job.type}</span>
                  </div>
                  <h3 className="font-display text-xl font-semibold mb-1 group-hover:text-primary transition-colors">{job.title}</h3>
                  <p className="text-sm font-medium text-muted-foreground mb-4">{job.company}</p>
                  <div className="flex items-center gap-4 text-sm text-muted-foreground">
                    <span className="flex items-center gap-1"><MapPin className="h-4 w-4" /> {job.location}</span>
                    {job.salary && <span className="flex items-center gap-1"><Briefcase className="h-4 w-4" /> {job.salary}</span>}
                  </div>
                </Link>
              </motion.div>
            ))}
          </div>
        )}
      </section>

      <footer className="border-t border-border py-10 text-center text-sm text-muted-foreground">
        © 2026 RecrutAI — Plateforme de recrutement en ligne.
      </footer>

      <ChatWidget />
    </div>
  );
}
