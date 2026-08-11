import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useDarkMode } from "@/context/DarkModeContext";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useTranslation } from "react-i18next";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import { Avatar } from "@/components/Avatar";
import { Briefcase, LogOut, LayoutDashboard, Sun, Moon, Bell, Sparkles, CalendarDays, FileText, MessageSquare, X, Trash2, Menu } from "lucide-react";

function notifRoute(n, role) {
  if (role === "admin") {
    if (n.type === "message" && n.candidate_id) return `/admin?section=messages&candidate=${n.candidate_id}&name=${encodeURIComponent(n.actor_name || "")}`;
    if (n.type === "application") return `/admin?section=applications${n.candidate_id ? `&profile=${n.candidate_id}` : ""}`;
    if (n.type === "screening") return `/admin?section=applications${n.candidate_id ? `&profile=${n.candidate_id}` : ""}`;
    if (n.type === "suggestion" && n.job_id) return `/admin?section=suggestions&job=${n.job_id}`;
    return "/admin";
  }
  if (n.type === "job" && n.job_id) return `/jobs/${n.job_id}`;
  if (n.type === "interview") return "/dashboard?section=interviews";
  if (n.type === "status") return "/dashboard?section=applications";
  if (n.type === "message") return "/dashboard?chat=1";
  return "/dashboard";
}

function NotifIcon({ n }) {
  if (n.actor_picture || (n.actor_name && n.type !== "suggestion")) {
    return <Avatar name={n.actor_name} src={n.actor_picture} size={38} />;
  }
  const map = { job: Briefcase, suggestion: Sparkles, interview: CalendarDays, application: FileText, screening: Sparkles, message: MessageSquare };
  const Icon = map[n.type] || Bell;
  return <div className="h-[38px] w-[38px] rounded-full bg-primary/10 text-primary flex items-center justify-center shrink-0"><Icon className="h-4 w-4" /></div>;
}

export function NotificationBell() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [data, setData] = useState({ items: [], unread: 0 });
  const load = () => api.get("/notifications").then(({ data }) => setData(data)).catch(() => {});
  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, []);
  const toggle = async () => {
    const n = !open; setOpen(n);
    if (n && data.unread > 0) { await api.post("/notifications/read-all").catch(() => {}); load(); }
  };
  const openNotif = (n) => {
    setOpen(false);
    navigate(notifRoute(n, user?.role));
    if (n.type === "message" && user?.role !== "admin") {
      setTimeout(() => window.dispatchEvent(new CustomEvent("open-support-chat")), 400);
    }
  };
  const delOne = async (e, id) => { e.stopPropagation(); await api.delete(`/notifications/${id}`).catch(() => {}); load(); };
  const clearAll = async () => { await api.delete("/notifications").catch(() => {}); load(); };
  return (
    <div className="relative">
      <button onClick={toggle} data-testid="notif-bell" aria-label="Notifications" className="relative h-9 w-9 rounded-full border border-border flex items-center justify-center hover:bg-secondary transition-colors">
        <Bell className="h-4 w-4" />
        {data.unread > 0 && <span className="absolute -top-1 -right-1 h-4 min-w-4 px-1 rounded-full bg-primary text-primary-foreground text-[10px] flex items-center justify-center" data-testid="notif-count">{data.unread}</span>}
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-80 max-h-96 overflow-y-auto rounded-xl border border-border bg-card shadow-xl z-50 p-2" data-testid="notif-panel">
          <div className="flex items-center justify-between px-1 pb-1.5">
            <span className="text-xs font-semibold text-muted-foreground">Notifications</span>
            {data.items.length > 0 && <button onClick={clearAll} data-testid="notif-clear-all" className="text-xs text-muted-foreground hover:text-destructive transition-colors">Tout effacer</button>}
          </div>
          {data.items.length === 0 ? (
            <p className="text-sm text-muted-foreground p-3 text-center">{t("nav.noNotifications")}</p>
          ) : data.items.map((n) => (
            <div key={n.id} className="group flex items-start gap-2 p-2 rounded-lg hover:bg-secondary transition-colors">
              <button onClick={() => openNotif(n)} data-testid={`notif-item-${n.id}`} className="flex items-start gap-3 text-left flex-1 min-w-0">
                <NotifIcon n={n} />
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium truncate">{n.actor_name ? n.actor_name : n.title}</p>
                  <p className="text-xs text-muted-foreground line-clamp-2">{n.body}</p>
                </div>
              </button>
              <button onClick={(e) => delOne(e, n.id)} data-testid={`notif-delete-${n.id}`} title="Supprimer" className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive transition-opacity mt-1 shrink-0"><X className="h-3.5 w-3.5" /></button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function Navbar() {
  const { user, logout } = useAuth();
  const { dark, toggle } = useDarkMode();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className="sticky top-0 z-40 glass border-b border-border">
      <div className="max-w-7xl mx-auto px-5 h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5" data-testid="nav-logo">
          <img src="/logo.png" alt="Talent Vortex" className="h-9 w-9 rounded-lg object-contain bg-white p-0.5" />
          <span className="font-display text-xl font-semibold">Talent Vortex</span>
        </Link>
        <nav className="flex items-center gap-2 sm:gap-3">
          <Link to="/" className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors hidden sm:block">
            {t("nav.offers")}
          </Link>
          {user && <NotificationBell />}

          <div className="hidden sm:flex items-center gap-3">
            <LanguageSwitcher />
            <button
              onClick={toggle}
              data-testid="dark-toggle-btn"
              aria-label="Basculer le thème"
              className="h-9 w-9 rounded-full border border-border flex items-center justify-center hover:bg-secondary transition-colors"
            >
              {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            </button>
            {user ? (
              <>
                <Button variant="ghost" onClick={() => navigate(user.role === "admin" ? "/admin" : "/dashboard")} data-testid="nav-dashboard-btn" className="rounded-full">
                  <LayoutDashboard className="h-4 w-4 mr-2" />
                  {user.role === "admin" ? t("nav.admin") : t("nav.mySpace")}
                </Button>
                <Button variant="outline" onClick={() => { logout(); navigate("/"); }} data-testid="nav-logout-btn" className="rounded-full">
                  <LogOut className="h-4 w-4" />
                </Button>
              </>
            ) : (
              <Button onClick={() => navigate("/login")} data-testid="nav-login-btn" className="rounded-full">
                {t("nav.login")}
              </Button>
            )}
          </div>

          <div className="sm:hidden relative">
            <button onClick={() => setMenuOpen((o) => !o)} data-testid="nav-hamburger-btn" aria-label="Menu" className="h-9 w-9 rounded-full border border-border flex items-center justify-center hover:bg-secondary transition-colors">
              {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </button>
            {menuOpen && (
              <div className="absolute right-0 top-full mt-2 w-56 rounded-xl border border-border bg-card shadow-xl z-50 p-3 flex flex-col gap-1.5" data-testid="nav-mobile-menu">
                {user ? (
                  <Button variant="default" onClick={() => { setMenuOpen(false); navigate(user.role === "admin" ? "/admin" : "/dashboard"); }} data-testid="mobile-dashboard-btn" className="rounded-full justify-start w-full">
                    <LayoutDashboard className="h-4 w-4 mr-2" />{user.role === "admin" ? t("nav.admin") : t("nav.mySpace")}
                  </Button>
                ) : (
                  <Button onClick={() => { setMenuOpen(false); navigate("/login"); }} data-testid="mobile-login-btn" className="rounded-full w-full">
                    {t("nav.login")}
                  </Button>
                )}
                <div className="h-px bg-border my-1" />
                <div className="flex items-center justify-between px-2 py-1.5">
                  <span className="text-sm text-muted-foreground">Langue</span>
                  <LanguageSwitcher />
                </div>
                <button onClick={toggle} data-testid="mobile-dark-toggle-btn" className="flex items-center justify-between px-2 py-2 rounded-lg hover:bg-secondary transition-colors text-sm">
                  <span className="text-muted-foreground">{dark ? "Mode clair" : "Mode sombre"}</span>
                  {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
                </button>
                <Link to="/" onClick={() => setMenuOpen(false)} className="text-sm font-medium px-2 py-2 rounded-lg hover:bg-secondary transition-colors">{t("nav.offers")}</Link>
                {user && (
                  <>
                    <div className="h-px bg-border my-1" />
                    <Button variant="outline" onClick={() => { setMenuOpen(false); logout(); navigate("/"); }} data-testid="mobile-logout-btn" className="rounded-full justify-start w-full">
                      <LogOut className="h-4 w-4 mr-2" /> Déconnexion
                    </Button>
                  </>
                )}
              </div>
            )}
          </div>
        </nav>
      </div>
    </header>
  );
}
