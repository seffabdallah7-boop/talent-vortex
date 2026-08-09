# Changelog — Talent Vortex

## 2026-06 (fork continuation)
### App rename
- "RecrutAI" → "Talent Vortex" partout (UI, emails, titre onglet, prompt IA, API root).

### Notifications & interviews (iteration 5)
- Notifications in-app pour l'admin sur nouvelle candidature + nouveau message.
- Notification + email au candidat quand un entretien est planifié (select candidat dans le formulaire admin).
- GET /interviews/me + vue entretiens côté candidat avec bouton "Rejoindre" (Jitsi).
- Cron rappels d'entretien (J-1) via .emergent/crons.yml + POST /api/cron/interview-reminders (secret WEBHOOK_CRON_SECRET).

### Phase Candidat (iteration 6) — 36/36 backend, frontend 100%
- Espace candidat repensé en layout sidebar : Mes postulations / Mes entretiens / Contrats obtenus / Mon profil, avec compteurs + badges de notifications.
- Profil candidat enrichi : nom, téléphone, nationalité, ville, pays, années d'expérience, poste actuel, domaines d'expertise, outils, titre, bio. Bannière "compléter le profil".
- Endpoints GET/PUT /api/profile (+ profile_completed) ; GET /api/contracts/me.
- Priorisation IA des offres : Claude détecte les domaines (ai_domains) ; GET /api/jobs classe les offres par match_score selon le domaine du candidat. Recherche `q` côté serveur.
- Anti double-candidature (POST /applications → 400) + bloc "déjà postulé" avec statut sur /jobs/:id.
- Lecteur audio du message vocal avec vitesse de lecture (1x/1.25x/1.5x/2x) — AudioPlayer.jsx.

### Phase Admin (partielle)
- IA Rédaction d'offre : POST /api/jobs/ai-draft — un brief/fiche de poste pré-remplit le formulaire d'offre (Claude), l'admin corrige puis publie. Panneau "Générer avec l'IA" dans le dialog nouvelle offre.
- Candidatures par offre : /jobs/all renvoie applicants + pending ; clic sur le compteur d'une offre filtre les candidatures (GET /applications?job_id=), chip "Candidatures pour : X" + "Voir toutes".
- Masquer/afficher une offre : Switch "Visible" → PUT /api/jobs/{id}/active (retire l'offre du listing public).
- Recherche de candidats : GET /api/users?q= (nom/email/poste/domaines/outils/nationalité/ville/pays) + colonnes Nationalité & Poste.

### Agenda (fait)
- Vue calendrier **semaine** dans l'agenda admin (bascule Semaine/Liste, navigation semaine précédente/suivante/Aujourd'hui, entretiens placés par jour, jour courant surligné, clic = éditer, Rejoindre).
- **Rappel 5 min avant** côté candidat : vérification toutes les 30s, bannière "Entretien imminent" + bouton Rejoindre + toast (fonctionne tant que l'app est ouverte).

### Chat enrichi (fait)
- Présence : POST /api/presence/ping (heartbeat 30s), GET /api/presence/admin. Statut "en ligne" si last_seen < 90s.
- Admin : pastille de présence par conversation + en-tête "En ligne / Hors ligne · vu il y a X".
- Candidat : en-tête présence admin dans le panneau Support.
- Heures sur chaque message + accusés de lecture ("✓ Envoyé" / "✓✓ Vu") côté candidat et admin.

### Appel vidéo pro (fait)
- Partage d'écran + coupure micro/caméra : natifs via la barre d'outils Jitsi (meet.jit.si), iframe autorisant display-capture.
- Bouton "Inviter" : copie le lien d'invitation de la salle (https://meet.jit.si/&lt;room&gt;) pour convier une personne externe.

### Traduction FR/EN (fondation)
- react-i18next + détection navigateur + persistance localStorage ("lang"). Sélecteur FR/EN global (LanguageSwitcher) dans la Navbar et la page Auth.
- Écrans traduits : Navbar, page d'accueil (hero, sections, features, footer), page de connexion/inscription/OTP/mot de passe oublié.
- Reste en français (extensible à la demande) : tableaux de bord internes admin/candidat, libellés issus de la base (catégories d'offres, statuts data).
