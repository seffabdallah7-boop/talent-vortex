import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Loader2 } from "lucide-react";

export default function AuthCallback() {
  const navigate = useNavigate();
  const { setSession } = useAuth();
  const processed = useRef(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (processed.current) return;
    processed.current = true;
    const hash = window.location.hash || "";
    const match = hash.match(/session_id=([^&]+)/);
    if (!match) {
      navigate("/login");
      return;
    }
    const sessionId = decodeURIComponent(match[1]);
    api
      .post("/auth/google/session", { session_id: sessionId })
      .then(({ data }) => {
        setSession(data.token, data.user);
        window.history.replaceState(null, "", window.location.pathname);
        navigate(data.user.role === "admin" ? "/admin" : "/dashboard", { replace: true });
      })
      .catch(() => {
        setError("Échec de la connexion Google.");
        setTimeout(() => navigate("/login"), 1500);
      });
  }, [navigate, setSession]);

  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-4" data-testid="auth-callback">
      <Loader2 className="h-8 w-8 animate-spin text-primary" />
      <p className="text-muted-foreground">{error || "Connexion en cours..."}</p>
    </div>
  );
}
