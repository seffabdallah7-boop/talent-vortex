import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { useDarkMode } from "@/context/DarkModeContext";
import { Button } from "@/components/ui/button";
import { Briefcase, LogOut, LayoutDashboard, Sun, Moon } from "lucide-react";

export default function Navbar() {
  const { user, logout } = useAuth();
  const { dark, toggle } = useDarkMode();
  const navigate = useNavigate();

  return (
    <header className="sticky top-0 z-40 glass border-b border-border">
      <div className="max-w-7xl mx-auto px-5 h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2.5" data-testid="nav-logo">
          <div className="h-9 w-9 rounded-lg bg-primary flex items-center justify-center">
            <Briefcase className="h-5 w-5 text-primary-foreground" />
          </div>
          <span className="font-display text-xl font-semibold">RecrutAI</span>
        </Link>
        <nav className="flex items-center gap-3">
          <Link to="/" className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors hidden sm:block">
            Offres
          </Link>
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
              <Button
                variant="ghost"
                onClick={() => navigate(user.role === "admin" ? "/admin" : "/dashboard")}
                data-testid="nav-dashboard-btn"
                className="rounded-full"
              >
                <LayoutDashboard className="h-4 w-4 mr-2" />
                {user.role === "admin" ? "Administration" : "Mon espace"}
              </Button>
              <Button variant="outline" onClick={() => { logout(); navigate("/"); }} data-testid="nav-logout-btn" className="rounded-full">
                <LogOut className="h-4 w-4" />
              </Button>
            </>
          ) : (
            <Button onClick={() => navigate("/login")} data-testid="nav-login-btn" className="rounded-full">
              Connexion
            </Button>
          )}
        </nav>
      </div>
    </header>
  );
}
