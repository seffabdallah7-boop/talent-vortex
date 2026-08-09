import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";

const resources = {
  fr: {
    translation: {
      nav: { offers: "Offres", mySpace: "Mon espace", admin: "Administration", login: "Connexion", noNotifications: "Aucune notification" },
      landing: {
        badge: "Recrutement nouvelle génération",
        heroLine1: "Votre voix", heroLine2: "au cœur du", heroLine3: "recrutement.",
        subtitle: "Déposez votre CV, enregistrez un message vocal jusqu'à 10 minutes et suivez le statut de chaque candidature — en toute transparence.",
        searchPlaceholder: "Poste, entreprise, ville...",
        seeJobs: "Voir les offres",
        recruited: "Des candidats recrutés chaque semaine",
        statusTitle: "Statut de candidature",
        statusAccepted: "Acceptée", statusPending: "En attente",
        sectionTitle: "Postuler n'a jamais été aussi humain.",
        sectionSubtitle: "Trois étapes, quelques minutes. Votre personnalité fait la différence.",
        f1t: "CV + Message vocal", f1d: "Joignez votre CV et enregistrez jusqu'à 10 minutes de motivation vocale.",
        f2t: "Assistant IA 24/7", f2d: "Un assistant intelligent répond à toutes vos questions, à tout moment.",
        f3t: "Suivi transparent", f3d: "En attente, acceptée ou refusée : suivez chaque statut en temps réel.",
        offersLabel: "Offres d'emploi",
        postsAvailable_one: "{{count}} poste disponible", postsAvailable_other: "{{count}} postes disponibles",
        noJobs: "Aucune offre pour le moment. Revenez bientôt !",
        footerTagline: "© 2026 Talent Vortex — Le recrutement qui vous ressemble.",
      },
      auth: {
        careerTitle: "Votre carrière commence ici.",
        careerSubtitle: "Rejoignez Talent Vortex et postulez aux meilleures offres avec votre CV et votre voix.",
        tabLogin: "Connexion", tabRegister: "Inscription",
        fullName: "Nom complet", email: "Email", password: "Mot de passe",
        passwordHint: "Min. 8 caractères, une lettre et un chiffre.",
        captchaLabel: "Vérification anti-robot",
        signIn: "Se connecter", createAccount: "Créer mon compte",
        forgot: "Mot de passe oublié ?",
        otpHintPrefix: "Saisissez le code à 6 chiffres envoyé à",
        otpLabel: "Code de vérification", otpVerify: "Vérifier et se connecter",
        back: "Retour",
        forgotHint: "Entrez votre email pour recevoir un code de réinitialisation.", sendCode: "Envoyer le code",
        resetHint: "Entrez le code reçu par email et votre nouveau mot de passe.",
        resetCode: "Code de réinitialisation", newPassword: "Nouveau mot de passe", resetBtn: "Réinitialiser",
        or: "OU", continueGoogle: "Continuer avec Google",
      },
    },
  },
  en: {
    translation: {
      nav: { offers: "Jobs", mySpace: "My space", admin: "Admin", login: "Sign in", noNotifications: "No notifications" },
      landing: {
        badge: "Next-generation recruitment",
        heroLine1: "Your voice", heroLine2: "at the heart of", heroLine3: "recruitment.",
        subtitle: "Upload your resume, record a voice message up to 10 minutes and track every application status — fully transparent.",
        searchPlaceholder: "Role, company, city...",
        seeJobs: "See jobs",
        recruited: "Candidates hired every week",
        statusTitle: "Application status",
        statusAccepted: "Accepted", statusPending: "Pending",
        sectionTitle: "Applying has never felt this human.",
        sectionSubtitle: "Three steps, a few minutes. Your personality makes the difference.",
        f1t: "Resume + Voice message", f1d: "Attach your resume and record up to 10 minutes of voice motivation.",
        f2t: "24/7 AI Assistant", f2d: "A smart assistant answers all your questions, anytime.",
        f3t: "Transparent tracking", f3d: "Pending, accepted or rejected: track every status in real time.",
        offersLabel: "Jobs",
        postsAvailable_one: "{{count}} job available", postsAvailable_other: "{{count}} jobs available",
        noJobs: "No jobs yet. Check back soon!",
        footerTagline: "© 2026 Talent Vortex — Recruitment that feels like you.",
      },
      auth: {
        careerTitle: "Your career starts here.",
        careerSubtitle: "Join Talent Vortex and apply to the best jobs with your resume and your voice.",
        tabLogin: "Sign in", tabRegister: "Sign up",
        fullName: "Full name", email: "Email", password: "Password",
        passwordHint: "Min. 8 characters, one letter and one digit.",
        captchaLabel: "Anti-robot check",
        signIn: "Sign in", createAccount: "Create account",
        forgot: "Forgot password?",
        otpHintPrefix: "Enter the 6-digit code sent to",
        otpLabel: "Verification code", otpVerify: "Verify and sign in",
        back: "Back",
        forgotHint: "Enter your email to receive a reset code.", sendCode: "Send code",
        resetHint: "Enter the code from your email and your new password.",
        resetCode: "Reset code", newPassword: "New password", resetBtn: "Reset",
        or: "OR", continueGoogle: "Continue with Google",
      },
    },
  },
};

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: "fr",
    supportedLngs: ["fr", "en"],
    interpolation: { escapeValue: false },
    detection: { order: ["localStorage", "navigator"], caches: ["localStorage"], lookupLocalStorage: "lang" },
  });

export default i18n;
