# RecrutAI — Plateforme de recrutement en ligne

## Original Problem Statement
Application web (React) de recrutement en ligne. Publier des offres ; les candidats postulent avec CV (document) + message vocal (jusqu'à 10 min) ; assistant IA répondant aux questions ; chat admin ↔ candidats ; compte administrateur avec rôles (supprimer candidats, recevoir/supprimer candidatures, changer les couleurs/design) ; statut de candidature (en attente / accepté / refusé) visible par le candidat ET l'admin. React Native prévu plus tard.

## User Choices
- Auth: JWT email/mot de passe + Google (Emergent-managed OAuth)
- Assistant IA: Claude Sonnet 4.6 (Emergent LLM key)
- Vocal: audio + transcription automatique (OpenAI Whisper)
- Chat admin↔candidat: polling
- Priorité: application web d'abord

## Architecture
- Frontend: React 19, react-router, TailwindCSS + Shadcn UI, framer-motion, lucide-react, sonner. Fonts: Clash Display (titres) + IBM Plex Sans.
- Backend: FastAPI (routes préfixées /api), Motor/MongoDB.
- Auth: Bearer token (localStorage), résout JWT ou session Google. Admin seedé au démarrage.
- Stockage fichiers: Emergent Object Storage (CV + audio), référencés en DB (soft-delete).
- IA: emergentintegrations LlmChat (anthropic/claude-sonnet-4-6) + OpenAISpeechToText (whisper-1, fr).
- Theming: variable CSS --primary stockée dans la collection `settings`, appliquée au chargement.

## User Personas
- Administrateur (seffabdallah7@gmail.com): gère offres, candidatures, candidats, messages, apparence.
- Candidat: parcourt les offres, postule (CV + vocal), suit ses statuts, discute avec l'admin / l'IA.

## Implemented (2026-06)
- Auth email/password (register/login/me) + Google OAuth callback ; rôles admin/candidat ; séparation des routes.
- Offres d'emploi: CRUD admin, listing public + recherche, page détail.
- Candidatures: soumission multipart (CV requis, vocal optionnel + transcription Whisper), listing candidat, listing admin + filtre statut, changement de statut, suppression.
- Statut visible des deux côtés (badges + timeline).
- Gestion candidats (liste + suppression en cascade).
- Chat admin↔candidat (polling) + widget candidat (onglets Assistant IA / Support).
- Assistant IA Claude Sonnet 4.6 (français, historique persistant).
- Apparence: presets + couleur personnalisée, persistée.
- Stats admin.
- Testé: 27/27 backend, flux frontend critiques OK.

## Roadmap validée avec l'utilisateur (ordre : Candidat → Admin → App)
### ✅ Phase Candidat (fait, 2026-06)
- Sidebar (postulations/entretiens/contrats/profil) + badges, profil enrichi + IA priorisation offres, anti-doublon, recherche, lecteur vocal avec vitesse.

### 🟡 Phase Admin (en cours)
- ✅ Regrouper les candidatures par offre (clic sur le compteur d'une offre → ses candidatures, chip + "Voir toutes") + badge "X nouv." (pending) sur chaque offre.
- ✅ Masquer/afficher une offre (Switch is_active) → PUT /api/jobs/{id}/active.
- ✅ Moteur de recherche de candidats (GET /api/users?q=) par nom/email/poste/domaines/outils/nationalité + colonnes Nationalité & Poste.
- ✅ IA Rédaction d'offre : POST /api/jobs/ai-draft (brief → formulaire pré-rempli, admin valide).
- Statut d'appréciation du candidat (rating/admin_note — déjà présent, à mettre en avant).
- ✅ Classification/statistiques des nationalités (GET /admin/nationalities + panneau admin).
- ✅ Agenda hebdomadaire (vue calendrier semaine, bascule Semaine/Liste) + rappel 5 min avant l'entretien (client, bannière + toast).
- ✅ Chat : accusés de lecture (vus) + heures, statut en ligne + dernière connexion (présence via ping/last_seen).

### 🟠 Phase Application (en cours)
- ✅ Appel vidéo entretien avancé : partage d'écran + mute micro/caméra (natifs Jitsi) + lien d'invitation (bouton "Inviter").
- ✅ Traduction FR/EN (fondation) : react-i18next + sélecteur global. Traduits : Navbar, accueil, auth. Écrans internes encore en FR (extensible).
- App React Native (mobile). **(PROCHAIN — selon crédit)**
- Fathom (à reconfirmer techniquement — non compatible Jitsi ; alternative résumé IA).
- Traduction FR/EN (react-i18next, sélecteur global).
- App React Native (mobile).

## Implemented (2026-06, itération 6)
- **Candidat — onglet Accueil** : nouvelle page par défaut du dashboard candidat listant toutes les offres (cartes), avec recherche, badge de compatibilité IA, bouton « Postuler » (→ /jobs/:id#postuler) ou statut (En attente / Accepté / Refusé) + « Voir » si déjà postulé. Plus besoin de repasser par la landing page.
- **Admin — photos/avatars partout** : composant `Avatar` (photo Google si dispo, sinon initiales colorées) affiché dans Candidatures, Utilisateurs et Messages (liste + en-tête de chat).
- **Admin — profil candidat riche** : `CandidateProfileDialog` ouvert au clic sur l'avatar/nom, affichant expertise (domaines/outils), bio, stats, candidatures avec statut + note interne, entretiens.
- Backend : `GET /api/users/{id}` (admin) → {user, applications, interviews, contracts} ; `/api/applications` enrichi de `candidate_picture` ; `/api/chat/conversations` enrichi de `picture`.
- Testé : 41/41 backend, 8/8 flux frontend (itération 6) — 100%.

## Next Tasks
- Traduire les tableaux de bord internes (Admin + Candidat) en FR/EN (P1).
- Filtre par nationalité cliquable dans le dashboard Admin (P2).
- Déploiement backend (prérequis app mobile React Native) via bouton Deploy.
