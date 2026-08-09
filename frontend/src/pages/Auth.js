import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth, formatApiError } from "@/context/AuthContext";
import { useDarkMode } from "@/context/DarkModeContext";
import { useTranslation } from "react-i18next";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Briefcase, Loader2, Sun, Moon, RefreshCw, ShieldCheck, ArrowLeft } from "lucide-react";
import { toast } from "sonner";

function CaptchaField({ question, value, onChange, onRefresh }) {
  const { t } = useTranslation();
  return (
    <div>
      <Label className="flex items-center gap-1.5"><ShieldCheck className="h-3.5 w-3.5" /> {t("auth.captchaLabel")}</Label>
      <div className="flex items-center gap-2 mt-1.5">
        <span className="px-3 h-11 flex items-center rounded-md bg-secondary font-mono font-semibold select-none" data-testid="captcha-question">{question} =</span>
        <Input data-testid="captcha-input" value={value} onChange={(e) => onChange(e.target.value)} required inputMode="numeric" placeholder="?" className="w-24" />
        <button type="button" onClick={onRefresh} data-testid="captcha-refresh" className="h-11 w-11 shrink-0 rounded-md border border-border flex items-center justify-center hover:bg-secondary"><RefreshCw className="h-4 w-4" /></button>
      </div>
    </div>
  );
}

export default function Auth() {
  const { setSession } = useAuth();
  const { dark, toggle } = useDarkMode();
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [tab, setTab] = useState("login");
  const [step, setStep] = useState("credentials"); // credentials | otp | forgot | reset
  const [form, setForm] = useState({ name: "", email: "", password: "", admin_code: "" });
  const [captcha, setCaptcha] = useState({ captcha_id: "", question: "..." });
  const [captchaAns, setCaptchaAns] = useState("");
  const [otp, setOtp] = useState("");
  const [pendingEmail, setPendingEmail] = useState("");
  const [reset, setReset] = useState({ email: "", code: "", new_password: "" });

  const go = (user) => navigate(user.role === "admin" ? "/admin" : "/dashboard");

  const refreshCaptcha = useCallback(async () => {
    setCaptchaAns("");
    try {
      const { data } = await api.get("/auth/captcha");
      setCaptcha(data);
    } catch (e) {}
  }, []);

  useEffect(() => { refreshCaptcha(); }, [refreshCaptcha]);

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      if (tab === "login") {
        const { data } = await api.post("/auth/login", {
          email: form.email, password: form.password,
          captcha_id: captcha.captcha_id, captcha_answer: captchaAns,
        });
        if (data.otp_required) {
          setPendingEmail(data.email);
          setStep("otp");
          toast.success("Un code de connexion vous a été envoyé par email.");
        }
      } else {
        const { data } = await api.post("/auth/register", {
          name: form.name, email: form.email, password: form.password,
          captcha_id: captcha.captcha_id, captcha_answer: captchaAns,
        });
        setSession(data.token, data.user);
        toast.success("Bienvenue " + data.user.name + " !");
        go(data.user);
      }
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail) || "Erreur");
      refreshCaptcha();
    } finally {
      setLoading(false);
    }
  };

  const verifyOtp = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await api.post("/auth/verify-otp", { email: pendingEmail, code: otp });
      setSession(data.token, data.user);
      toast.success("Bienvenue " + data.user.name + " !");
      go(data.user);
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail) || "Code incorrect");
    } finally {
      setLoading(false);
    }
  };

  const submitForgot = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await api.post("/auth/forgot-password", { email: reset.email, captcha_id: captcha.captcha_id, captcha_answer: captchaAns });
      toast.success("Si le compte existe, un code de réinitialisation a été envoyé.");
      setStep("reset");
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail) || "Erreur");
      refreshCaptcha();
    } finally {
      setLoading(false);
    }
  };

  const submitReset = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      await api.post("/auth/reset-password", { email: reset.email, code: reset.code, new_password: reset.new_password });
      toast.success("Mot de passe réinitialisé. Connectez-vous.");
      setStep("credentials");
      setTab("login");
      refreshCaptcha();
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail) || "Erreur");
    } finally {
      setLoading(false);
    }
  };

  const CaptchaFieldEl = (
    <CaptchaField question={captcha.question} value={captchaAns} onChange={setCaptchaAns} onRefresh={refreshCaptcha} />
  );

  const googleLogin = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    const redirectUrl = window.location.origin + "/dashboard";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2 relative">
      <button
        onClick={toggle}
        data-testid="auth-dark-toggle"
        aria-label="Basculer le thème"
        className="absolute top-4 right-4 z-20 h-9 w-9 rounded-full border border-border bg-card flex items-center justify-center hover:bg-secondary transition-colors"
      >
        {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
      </button>
      <div className="hidden lg:block relative grain">
        <img
          src="https://images.unsplash.com/photo-1560250097-0b93528c311a?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjAzMzN8MHwxfHNlYXJjaHwxfHxwcm9mZXNzaW9uYWwlMjBvZmZpY2UlMjB3b3JrZXIlMjBwb3J0cmFpdHxlbnwwfHx8fDE3ODYyMTY1Nzh8MA&ixlib=rb-4.1.0&q=85"
          alt=""
          className="absolute inset-0 w-full h-full object-cover"
        />
        <div className="absolute inset-0 bg-primary/70 mix-blend-multiply" />
        <div className="relative h-full flex flex-col justify-end p-12 text-white">
          <h2 className="font-display text-4xl font-semibold leading-tight">{t("auth.careerTitle")}</h2>
          <p className="text-white/80 mt-4 max-w-sm">{t("auth.careerSubtitle")}</p>
        </div>
      </div>

      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <div onClick={() => navigate("/")} className="flex items-center gap-2.5 mb-8 cursor-pointer" data-testid="auth-logo">
            <div className="h-9 w-9 rounded-lg bg-primary flex items-center justify-center">
              <Briefcase className="h-5 w-5 text-primary-foreground" />
            </div>
            <span className="font-display text-xl font-semibold">Talent Vortex</span>
          </div>

          <Tabs value={tab} onValueChange={(v) => { setTab(v); setStep("credentials"); refreshCaptcha(); }}>
            <TabsList className="grid grid-cols-2 w-full mb-6">
              <TabsTrigger value="login" data-testid="tab-login">{t("auth.tabLogin")}</TabsTrigger>
              <TabsTrigger value="register" data-testid="tab-register">{t("auth.tabRegister")}</TabsTrigger>
            </TabsList>

            {step === "credentials" && (
              <form onSubmit={submit} className="space-y-4">
                <TabsContent value="register" className="mt-0 space-y-4">
                  <div>
                    <Label htmlFor="name">{t("auth.fullName")}</Label>
                    <Input id="name" data-testid="register-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required={tab === "register"} className="mt-1.5" />
                  </div>
                </TabsContent>
                <div>
                  <Label htmlFor="email">{t("auth.email")}</Label>
                  <Input id="email" type="email" data-testid="auth-email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required className="mt-1.5" />
                </div>
                <div>
                  <Label htmlFor="password">{t("auth.password")}</Label>
                  <Input id="password" type="password" data-testid="auth-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required className="mt-1.5" />
                  {tab === "register" && <p className="text-xs text-muted-foreground mt-1">{t("auth.passwordHint")}</p>}
                </div>
                {CaptchaFieldEl}
                <Button type="submit" disabled={loading} className="w-full rounded-full h-11" data-testid="auth-submit-btn">
                  {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : tab === "login" ? t("auth.signIn") : t("auth.createAccount")}
                </Button>
                {tab === "login" && (
                  <button type="button" onClick={() => { setStep("forgot"); setReset({ email: form.email, code: "", new_password: "" }); refreshCaptcha(); }} data-testid="forgot-link" className="w-full text-center text-sm text-muted-foreground hover:text-primary transition-colors">
                    {t("auth.forgot")}
                  </button>
                )}
              </form>
            )}

            {step === "otp" && (
              <form onSubmit={verifyOtp} className="space-y-4">
                <p className="text-sm text-muted-foreground">{t("auth.otpHintPrefix")} <b>{pendingEmail}</b>.</p>
                <div>
                  <Label htmlFor="otp">{t("auth.otpLabel")}</Label>
                  <Input id="otp" data-testid="otp-input" value={otp} onChange={(e) => setOtp(e.target.value)} required inputMode="numeric" maxLength={6} placeholder="000000" className="mt-1.5 tracking-[0.5em] text-center font-mono text-lg" />
                </div>
                <Button type="submit" disabled={loading} className="w-full rounded-full h-11" data-testid="otp-verify-btn">
                  {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : t("auth.otpVerify")}
                </Button>
                <button type="button" onClick={() => setStep("credentials")} className="w-full text-center text-sm text-muted-foreground hover:text-primary flex items-center justify-center gap-1"><ArrowLeft className="h-3.5 w-3.5" /> {t("auth.back")}</button>
              </form>
            )}

            {step === "forgot" && (
              <form onSubmit={submitForgot} className="space-y-4">
                <p className="text-sm text-muted-foreground">{t("auth.forgotHint")}</p>
                <div>
                  <Label htmlFor="fe">{t("auth.email")}</Label>
                  <Input id="fe" type="email" data-testid="forgot-email" value={reset.email} onChange={(e) => setReset({ ...reset, email: e.target.value })} required className="mt-1.5" />
                </div>
                {CaptchaFieldEl}
                <Button type="submit" disabled={loading} className="w-full rounded-full h-11" data-testid="forgot-submit-btn">
                  {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : t("auth.sendCode")}
                </Button>
                <button type="button" onClick={() => { setStep("credentials"); refreshCaptcha(); }} className="w-full text-center text-sm text-muted-foreground hover:text-primary flex items-center justify-center gap-1"><ArrowLeft className="h-3.5 w-3.5" /> {t("auth.back")}</button>
              </form>
            )}

            {step === "reset" && (
              <form onSubmit={submitReset} className="space-y-4">
                <p className="text-sm text-muted-foreground">{t("auth.resetHint")}</p>
                <div>
                  <Label htmlFor="rc">{t("auth.resetCode")}</Label>
                  <Input id="rc" data-testid="reset-code" value={reset.code} onChange={(e) => setReset({ ...reset, code: e.target.value })} required inputMode="numeric" maxLength={6} placeholder="000000" className="mt-1.5 tracking-[0.4em] text-center font-mono" />
                </div>
                <div>
                  <Label htmlFor="rp">{t("auth.newPassword")}</Label>
                  <Input id="rp" type="password" data-testid="reset-password" value={reset.new_password} onChange={(e) => setReset({ ...reset, new_password: e.target.value })} required className="mt-1.5" />
                  <p className="text-xs text-muted-foreground mt-1">{t("auth.passwordHint")}</p>
                </div>
                <Button type="submit" disabled={loading} className="w-full rounded-full h-11" data-testid="reset-submit-btn">
                  {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : t("auth.resetBtn")}
                </Button>
                <button type="button" onClick={() => { setStep("credentials"); refreshCaptcha(); }} className="w-full text-center text-sm text-muted-foreground hover:text-primary flex items-center justify-center gap-1"><ArrowLeft className="h-3.5 w-3.5" /> {t("auth.back")}</button>
              </form>
            )}
          </Tabs>

          {step === "credentials" && (
          <>
          <div className="flex items-center gap-3 my-5">
            <div className="flex-1 h-px bg-border" />
            <span className="text-xs text-muted-foreground">{t("auth.or")}</span>
            <div className="flex-1 h-px bg-border" />
          </div>

          <Button variant="outline" onClick={googleLogin} className="w-full rounded-full h-11" data-testid="google-login-btn">
            <svg className="h-5 w-5 mr-2" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1Z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23Z"/><path fill="#FBBC05" d="M5.84 14.1a6.6 6.6 0 0 1 0-4.2V7.06H2.18a11 11 0 0 0 0 9.88l3.66-2.84Z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1A11 11 0 0 0 2.18 7.06l3.66 2.84C6.71 7.31 9.14 5.38 12 5.38Z"/></svg>
            {t("auth.continueGoogle")}
          </Button>
          </>
          )}
        </div>
      </div>
    </div>
  );
}
