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
