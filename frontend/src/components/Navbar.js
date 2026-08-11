import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useDarkMode } from "@/context/DarkModeContext";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useTranslation } from "react-i18next";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import { Briefcase, LogOut, LayoutDashboard, Sun, Moon, Bell } from "lucide-react";

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
  const openNotif = () => {
    setOpen(false);
    navigate(user?.role === "admin" ? "/admin" : "/dashboard");
  };
  return (
    <div className="relative">
      <button onClick={toggle} data-testid="notif-bell" aria-label="Notifications" className="relative h-9 w-9 rounded-full border border-border flex items-center justify-center hover:bg-secondary transition-colors">
        <Bell className="h-4 w-4" />
        {data.unread > 0 && <span className="absolute -top-1 -right-1 h-4 min-w-4 px-1 rounded-full bg-primary text-primary-foreground text-[10px] flex items-center justify-center" data-testid="notif-count">{data.unread}</span>}
      </button>
      {open && (
        <div className="absolute right-0 mt-2 w-72 max-h-80 overflow-y-auto rounded-xl border border-border bg-card shadow-xl z-50 p-2" data-testid="notif-panel">
          {data.items.length === 0 ? (
            <p className="text-sm text-muted-foreground p-3 text-center">{t("nav.noNotifications")}</p>
          ) : data.items.map((n) => (
            <button key={n.id} onClick={openNotif} data-testid={`notif-item-${n.id}`} className="w-full text-left p-3 rounded-lg hover:bg-secondary transition-colors">
              <p className="text-sm font-medium">{n.title}</p>
              <p className="text-xs text-muted-foreground">{n.body}</p>
            </button>
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

  return (
    <header className="sticky top-0 z-40 glass border-b border-border">
      <div className="max-w-7xl mx-auto px-5 h-16 flex items-center justify-between">
        <Link to={user ? (user.role === "admin" ? "/admin" : "/dashboard") : "/"} className="flex items-center gap-2.5" data-testid="nav-logo">
          <div className="h-9 w-9 rounded-lg bg-primary flex items-center justify-center">
            <Briefcase className="h-5 w-5 text-primary-foreground" />
          </div>
          <span className="font-display text-xl font-semibold">Talent Vortex</span>
        </Link>
        <nav className="flex items-center gap-3">
          <Link to="/" className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors hidden sm:block">
            {t("nav.offers")}
          </Link>
          <LanguageSwitcher />
          <button
            onClick={toggle}
            data-testid="dark-toggle-btn"
            aria-label="Basculer le thème"
            className="h-9 w-9 rounded-full border border-border flex items-center justify-center hover:bg-secondary transition-colors"
          >
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>
          {user && <NotificationBell />}
          {user ? (
            <>
              <Button
                variant="ghost"
                onClick={() => navigate(user.role === "admin" ? "/admin" : "/dashboard")}
                data-testid="nav-dashboard-btn"
                className="rounded-full"
              >
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
        </nav>
      </div>
    </header>
  );
}
