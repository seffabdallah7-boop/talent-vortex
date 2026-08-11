import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { useTranslation } from "react-i18next";
import api from "@/lib/api";
import Navbar from "@/components/Navbar";
import ChatWidget from "@/components/ChatWidget";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MapPin, Briefcase, Search, ArrowRight, FileAudio, ShieldCheck, Bot, MoveUpRight, Star } from "lucide-react";

const HERO = "https://static.prod-images.emergentagent.com/jobs/ad379664-d6fd-49f5-b212-fa711498c483/images/c22824a5a6045698503ab5f468121c8e1737b885742b22d5f16531bedca176e1.jpeg";
const AV1 = "https://images.unsplash.com/photo-1560250097-0b93528c311a?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMzN8MHwxfHNlYXJjaHwxfHxwcm9mZXNzaW9uYWwlMjBvZmZpY2UlMjB3b3JrZXIlMjBwb3J0cmFpdHxlbnwwfHx8fDE3ODYyMTY1Nzh8MA&ixlib=rb-4.1.0&q=85";
const AV2 = "https://images.pexels.com/photos/8101982/pexels-photo-8101982.jpeg?auto=compress&cs=tinysrgb&dpr=2&h=650&w=940";
const CATS = ["Tech", "Ressources Humaines", "Design", "Data", "Marketing", "Finance"];

export default function Landing() {
  const { t } = useTranslation();
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
    <div className="App bg-background text-foreground">
      <Navbar />

      <section className="relative overflow-hidden border-b border-border">
        {/* Image professionnelle en arrière-plan (droite), fondue dans la page */}
        <div className="absolute inset-y-0 right-0 w-full lg:w-[62%] pointer-events-none">
          <img src={HERO} alt="Recruteurs professionnels" className="h-full w-full object-cover object-top" />
          <div className="absolute inset-0 bg-gradient-to-r from-background via-background/85 to-background/10 lg:via-background/55" />
          <div className="absolute inset-0 bg-gradient-to-t from-background via-background/25 to-transparent" />
        </div>
        <div className="absolute inset-0 dot-grid opacity-30 pointer-events-none" />

        <div className="relative max-w-7xl mx-auto px-5 pt-16 pb-24 md:pt-24 md:pb-32">
          <div className="max-w-xl lg:max-w-2xl">
            <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} className="inline-flex items-center gap-2 rounded-full border border-border bg-card/80 backdrop-blur px-3 py-1.5 mb-7">
              <span className="h-2 w-2 rounded-full bg-primary animate-pulse" />
              <span className="label-caps text-muted-foreground">{t("landing.badge")}</span>
            </motion.div>
            <h1 className="font-display text-5xl sm:text-6xl lg:text-7xl font-semibold leading-[0.95]">
              <motion.span initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="block">{t("landing.heroLine1")}</motion.span>
              <motion.span initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.12 }} className="block text-stroke">{t("landing.heroLine2")}</motion.span>
              <motion.span initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.19 }} className="block">{t("landing.heroLine3")}</motion.span>
            </h1>
            <motion.p initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.26 }} className="text-base md:text-lg text-muted-foreground max-w-lg mt-7">
              {t("landing.subtitle")}
            </motion.p>
            <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.33 }} className="mt-8 flex flex-col sm:flex-row gap-3 max-w-lg">
              <div className="relative flex-1">
                <Search className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-muted-foreground" />
                <Input
                  data-testid="job-search-input"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder={t("landing.searchPlaceholder")}
                  className="pl-12 h-12 rounded-none border-2 border-foreground/15 focus-visible:border-primary bg-card"
                />
              </div>
              <Button asChild className="rounded-none h-12 px-8" data-testid="hero-cta">
                <a href="#offres">{t("landing.seeJobs")} <ArrowRight className="h-4 w-4 ml-2" /></a>
              </Button>
            </motion.div>
            <div className="mt-8 flex items-center gap-3 text-sm text-muted-foreground">
              <div className="flex -space-x-2">
                {[AV1, AV2].map((s, i) => (
                  <img key={i} src={s} className="h-8 w-8 rounded-full border-2 border-background object-cover" alt="" />
                ))}
                <span className="h-8 w-8 rounded-full border-2 border-background bg-primary text-primary-foreground text-xs font-semibold flex items-center justify-center">+9</span>
              </div>
              <span>{t("landing.recruited")}</span>
            </div>
          </div>
        </div>

        {/* Carte statut flottante en glass par-dessus l'image (desktop) */}
        <motion.div
          initial={{ opacity: 0, y: 24 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.45 }}
          className="hidden lg:block absolute right-6 xl:right-12 bottom-10 z-10 w-80 glass rounded-2xl border border-border/60 shadow-2xl p-5"
        >
          <p className="label-caps text-muted-foreground mb-3">Statut de candidature</p>
          <div className="space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Développeur Full-Stack</span>
              <span className="status-accepted rounded-full px-2.5 py-0.5 text-xs font-semibold">{t("landing.statusAccepted")}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium">Designer UI/UX</span>
              <span className="status-pending rounded-full px-2.5 py-0.5 text-xs font-semibold">En attente</span>
            </div>
          </div>
        </motion.div>
      </section>

      <div className="border-b border-border overflow-hidden py-4 bg-card">
        <div className="flex whitespace-nowrap animate-marquee">
          {[...CATS, ...CATS].map((c, i) => (
            <span key={i} className="mx-6 font-display text-2xl font-semibold text-muted-foreground/50 flex items-center gap-6">
              {c}<Star className="h-4 w-4 text-primary" />
            </span>
          ))}
        </div>
      </div>

      <section className="max-w-7xl mx-auto px-5 py-20">
        <div className="flex items-end justify-between mb-12 flex-wrap gap-4">
          <h2 className="font-display text-3xl lg:text-5xl font-semibold max-w-md leading-tight">{t("landing.sectionTitle")}</h2>
          <p className="text-muted-foreground max-w-sm">{t("landing.sectionSubtitle")}</p>
        </div>
        <div className="grid md:grid-cols-3 gap-px bg-border border border-border">
          {[
            { n: "01", Icon: FileAudio, t: t("landing.f1t"), d: t("landing.f1d") },
            { n: "02", Icon: Bot, t: t("landing.f2t"), d: t("landing.f2d") },
            { n: "03", Icon: ShieldCheck, t: t("landing.f3t"), d: t("landing.f3d") },
          ].map((f, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.08 }}
              className="group bg-background p-8 hover:bg-card transition-colors"
            >
              <div className="flex items-center justify-between mb-8">
                <span className="font-display text-4xl font-semibold text-primary">{f.n}</span>
                <f.Icon className="h-6 w-6 text-muted-foreground group-hover:text-primary transition-colors" />
              </div>
              <h3 className="font-display text-xl font-semibold mb-2">{f.t}</h3>
              <p className="text-muted-foreground leading-relaxed">{f.d}</p>
            </motion.div>
          ))}
        </div>
      </section>

      <section id="offres" className="max-w-7xl mx-auto px-5 pb-24">
        <div className="flex items-end justify-between mb-10 border-t-2 border-foreground/15 pt-8">
          <div>
            <p className="label-caps text-primary mb-2">{t("landing.offersLabel")}</p>
            <h2 className="font-display text-3xl lg:text-5xl font-semibold">{t("landing.postsAvailable", { count: filtered.length })}</h2>
          </div>
        </div>

        {filtered.length === 0 ? (
          <div className="border-2 border-dashed border-border p-16 text-center text-muted-foreground" data-testid="no-jobs">
            {t("landing.noJobs")}
          </div>
        ) : (
          <div className="max-h-[72vh] overflow-y-auto overflow-x-hidden pr-1.5 -mr-1.5 rounded-xl scroll-smooth" data-testid="offers-scroll">
            <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4 pb-1">
            {filtered.map((job, i) => {
              const featured = i === 0;
              return (
                <motion.div
                  key={job.id}
                  initial={{ opacity: 0, y: 16 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: (i % 3) * 0.06 }}
                  className={featured ? "lg:col-span-2" : ""}
                >
                  <Link
                    to={`/jobs/${job.id}`}
                    data-testid={`job-card-${job.id}`}
                    className={`group relative flex h-full flex-col border-2 border-foreground/15 bg-card p-6 transition-colors hover:border-primary ${featured ? "lg:p-8" : ""}`}
                  >
                    <div className="flex items-center gap-2 mb-4">
                      <span className="text-xs font-semibold border border-foreground/15 px-3 py-1">{job.category}</span>
                      <span className="text-xs text-muted-foreground">{job.type}</span>
                      {job.match_percent && (
                        <span className="text-xs font-bold text-primary bg-primary/10 rounded-full px-2.5 py-1 flex items-center gap-1" data-testid={`match-badge-${job.id}`}>
                          <Star className="h-3 w-3 fill-primary" /> {t("landing.match", { percent: job.match_percent })}
                        </span>
                      )}
                      <MoveUpRight className="ml-auto h-5 w-5 text-muted-foreground transition-transform group-hover:text-primary group-hover:-translate-y-0.5 group-hover:translate-x-0.5" />
                    </div>
                    <h3 className={`font-display font-semibold mb-1 group-hover:text-primary transition-colors ${featured ? "text-2xl lg:text-3xl" : "text-xl"}`}>{job.title}</h3>
                    <p className="text-sm font-medium text-muted-foreground mb-4">{job.company}</p>
                    {featured && <p className="text-muted-foreground mb-6 line-clamp-2 max-w-lg">{job.description}</p>}
                    <div className="mt-auto flex items-center gap-4 text-sm text-muted-foreground">
                      <span className="flex items-center gap-1"><MapPin className="h-4 w-4" /> {job.location}</span>
                      {job.salary && <span className="flex items-center gap-1"><Briefcase className="h-4 w-4" /> {job.salary}</span>}
                    </div>
                  </Link>
                </motion.div>
              );
            })}
            </div>
          </div>
        )}
      </section>

      <footer className="border-t-2 border-foreground/15">
        <div className="max-w-7xl mx-auto px-5 py-14 flex flex-col md:flex-row items-start md:items-center justify-between gap-6">
          <div>
            <div className="flex items-center gap-2.5 mb-2">
              <img src="/logo.png" alt="Talent Vortex" className="h-9 w-9 rounded-lg object-contain bg-white p-0.5" />
              <span className="font-display text-xl font-semibold">Talent Vortex</span>
            </div>
            <p className="text-sm text-muted-foreground">{t("landing.footerTagline")}</p>
          </div>
          <a href="#offres" className="group font-display text-2xl md:text-3xl font-semibold flex items-center gap-2 hover:text-primary transition-colors">
            {t("landing.seeJobs")} <MoveUpRight className="h-6 w-6 transition-transform group-hover:-translate-y-1 group-hover:translate-x-1" />
          </a>
        </div>
      </footer>

      <ChatWidget />
    </div>
  );
}
