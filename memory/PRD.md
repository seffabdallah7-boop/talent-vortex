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

## Implemented (2026-06, itération 7-8 — Phase A : navigation & interactivité)
- **Dashboard admin interactif** : toutes les cartes/compteurs sont cliquables → redirigent vers la liste filtrée (Offres, Candidats, Candidatures all/pending/accepted/rejected, Contrats en_cours, Entretiens).
- **Lignes cliquables** : offres (→ /jobs/:id détail), contrats (→ dialogue détail/édition).
- **Sidebar responsive** : bouton menu hamburger (haut-gauche) + drawer sur mobile/tablette, côté admin ET candidat.
- **Cartes offres candidat** : titre cliquable → page détail.
- **Notifications cliquables** : items de la cloche → redirigent vers le dashboard ; cloche ajoutée dans le dashboard admin (desktop + mobile).
- Testé : 100% des flux Phase A (itérations 7-8).

## Roadmap restante (validée avec l'utilisateur, juin 2026)
- ✅ **Phase B — Appréciation admin** : colonne ★ (moyenne des ratings de candidatures) dans Utilisateurs + filtre `rating-filter` (min_rating). Backend `/users?min_rating=N`. Testé 100%.
- ✅ **Phase C — Flux entretien** : bouton « Accepter » → dialogue « Planifier l'entretien » pré-rempli → POST /interviews → apparaît dans l'espace candidat (Mes entretiens) + notification. Testé 100%.
- ✅ **Phase D — Notifications auto d'offres** : à la création d'une offre, `notify_matching_candidates` notifie (type "job") chaque candidat dont domains/ai_domains correspondent. Vérifié via curl.
- 🟠 **Phase E — Appels audio/vidéo intégrés (Jitsi)** ✅ FAIT & testé : boutons Discuter/Appel audio/Appel vidéo dans la fiche candidat ; appel entrant côté candidat (sonnerie Web Audio + décrocher, polling /calls/incoming) ; salle de réunion admin (`nav-meeting`) ; **enregistrement navigateur → stockage objet → transcription Whisper → résumé IA Claude** affiché dans la page admin « Enregistrements » (`nav-recordings`). Backend 12/12, frontend 100%.
- 🟠 **Phase F — Auth** ✅ FAIT & vérifié : plus d'OTP email à la connexion (POST /auth/login renvoie directement token+user, captcha conservé) ; token JWT 14 jours + POST /auth/refresh au chargement (session glissante 2 semaines).
- 🟠 **Phase G — IA de pré-qualification par chat** ✅ FAIT & vérifié : à la candidature, l'IA (Claude) génère 4 questions selon la fiche de poste ; le candidat y répond (quiz auto-ouvert + bouton dans « Mes postulations ») ; l'IA évalue (verdict + score/100 + analyse) ; l'admin est notifié et consulte via le bouton « Voir l'examen IA » (confidentiel — champs IA non exposés au candidat).
- ✅ **Nettoyage auto des vidéos** : cron hebdo `POST /api/cron/cleanup-recordings` supprime les enregistrements > `RECORDING_RETENTION_MONTHS` (défaut 6 mois).
- 🔵 **Phase H — Traduction complète FR/EN** ✅ FAIT & testé (6/6) : traducteur automatique réversible (`useAutoTranslate` + dictionnaire `uiDict.js`) monté à la racine → bascule tout le site (pages publiques via i18next + tableaux de bord internes) sans altérer les données dynamiques (noms, intitulés d'offres). Sélecteur FR/EN ajouté dans le dashboard admin (le candidat l'a déjà via la Navbar).

## Implemented (2026-06, itération 16 — Messagerie/Vidéo + Suggestions IA)
- **Chat candidat verrouillé** (point 7) : la saisie du support reste inactive tant que l'admin n'a pas initié la conversation (`GET /api/chat/unread` → has_admin). Notice `chat-locked-notice`.
- **Notifications de messages** (points 1&4) : pastille de non-lus `chat-unread-badge` sur le bouton flottant du chat candidat + emails hors-ligne (déjà backend).
- **Redirection quiz IA** (point 2) : après candidature, redirection immédiate vers `/dashboard?section=applications` avec ouverture auto du ScreeningQuiz.
- **Lien vidéo partageable protégé** (point 6) : `POST /api/recordings/{id}/share` + page `/recordings/shared/:token` (ProtectedRoute admin) ; bouton « Lien » dans Admin > Enregistrements.
- **Téléchargement vidéo** (point 5) : bouton « Vidéo » (download .webm) dans Admin > Enregistrements.
- **Suggestions IA de candidats par offre** (point 8) : `GET /api/jobs/{id}/suggestions` (Claude classe les profils candidats par score de compatibilité + raison, fallback heuristique). Nouvelle section admin « Suggestions IA » (nav-suggestions), offres dépliables → candidats classés cliquables (ouvre le profil).
- Testé itération 16 : backend 100% (8/8), frontend points 7/2/6 OK ; nav Suggestions ré-ajouté après correctif.
- **Design** : image hero de la landing remplacée par un visuel professionnel généré (femme noire + homme en costume, bureau moderne avec skyline).

## Implemented (2026-06, itération 17 — Publication/Notifications/Design)
- **Récap suggestions à la publication** : à la création d'une offre, tâche de fond `notify_admin_suggestions` → notification in-app + email au recruteur avec le top 3 des profils (score + raison). Logique factorisée `compute_job_suggestions`.
- **Header admin** : cloche notifications, sélecteur de langue et mode sombre déplacés dans un header collant en haut de page (`admin-header`) ; sidebar = email + déconnexion.
- **Notifications cliquables + profils** : `GET /api/notifications` enrichi (actor_name/actor_picture du concerné). Clic → routage ciblé (admin : messages/candidate, applications/profile, suggestions/job ; candidat : /jobs/:id, section interviews/applications, ouverture du chat support). Avatar affiché dans chaque item (repli icône par type).
- **Hero landing redesign** : image du duo pro en arrière-plan (droite) fondue par dégradé, carte statut flottante en glass — vérifié light/dark.

## Implemented (2026-06, itération 18 — Chat complet + Notifications + Listes)
- **Chat enrichi (2 côtés)** : envoi image/document, message vocal (MediaRecorder), édition et suppression de message. Bulle réutilisable `ChatMessageBubble.jsx`. Backend : `POST /chat/attachments`, `PUT/DELETE /chat/messages/{id}`, accès fichier élargi aux participants de la conversation. Côté admin : heure du dernier message dans la liste des conversations.
- **Notifications** : plus de notification in-app par message (anti-débordement, seul le badge du chat + email hors-ligne). Auto-purge des notifications lues > 7 jours (opportuniste + cron `cleanup-notifications`). Suppression manuelle (✕ par item + « Tout effacer »).
- **Candidatures** : recherche (candidat/email/poste) + filtre par offre + suppression par ligne.
- **Suppression généralisée** : toutes les listes admin disposent d'un delete.

## Implemented (2026-06, itération 22 — Filtre conversations + frappe rapide + accusés de lecture)
- **Filtre conversations admin** : segmenté Toutes/Actives/Inactives.
- **Frappe plus réactive** : polling messages à 2 s quand le chat est ouvert (candidat + admin).
- **Accusés de lecture enrichis** : `read_at` stocké au marquage lu ; infobulle « Lu à HH:MM » au survol du statut du message.

## Implemented (2026-06, itération 21 — Badges de messages non lus)
- **Badge menu admin** : nombre total de messages non lus affiché sur l'item « Messages » (somme des conversations, poll 10 s).
- **Badge menu candidat** : item « Messagerie recruteur » (visible si conversation active) avec compteur de messages recruteur non lus ; clic ouvre le chat. Validé par curl (admin=3, candidat=1).

## Implemented (2026-06, itération 20 — Email d'invitation + indicateur de frappe)
- **Email d'invitation** : à l'activation d'une conversation, le candidat reçoit un email (`_invite_email_html`) l'invitant à ouvrir la « Messagerie recruteur » (en plus de la notification in-app).
- **Indicateur de frappe** : `POST /chat/typing` + `other_typing` dans `GET /chat/messages` ; « en train d'écrire… » affiché des deux côtés (validé par curl, bidirectionnel).

## Implemented (2026-06, itération 19 — Conversations activables + séparation IA/recruteur)
- **VALIDÉ UI (iteration_19, tous scénarios PASS)** : activation/désactivation admin, carte candidat conditionnelle, séparation IA/recruteur, séparateur « Nouveaux messages » + auto-scroll.
- **Activation/désactivation par l'admin** : `conversations.active` (collection dédiée) + `PUT /chat/conversations/{id}/active`. La liste admin montre le flag actif/inactif et un sélecteur « Nouvelle discussion » pour démarrer/activer un candidat.
- **Accès candidat conditionnel** : `GET /chat/unread` renvoie `active` ; carte « Messagerie recruteur » (`recruiter-chat-card`) sur le dashboard candidat visible uniquement si active, avec bouton d'ouverture + compteur de non-lus.
- **Séparation IA / recruteur** : suppression des onglets du widget ; l'assistant IA reste le widget flottant, la messagerie recruteur s'ouvre via la carte du dashboard (event `open-support-chat`). Verrou basé sur `active` (au lieu de has_admin).
- **Premier message non lu** : `GET /chat/messages` renvoie `{messages, first_unread}` ; séparateur « Nouveaux messages » affiché côté candidat et admin avant le 1er non-lu.

## Implemented (2026-06, itération 23 — Refactoring backend + UX)
- **Refactoring backend (server.py 2160→75 lignes)** : découpage modulaire en `core.py` (config, db, storage, sécurité, dépendances auth, templates email, notifications, transcribe_audio) + `routers/` (`auth`, `jobs`, `applications`, `users`, `chat`, `calls`, `interviews`, `contracts`, `misc`). `server.py` ne fait plus que câbler les routers + startup/shutdown. Comportement préservé (aucun chemin d'API modifié). Régression testée 24/24 backend.
- **Landing — offres scrollables** : la liste des offres est désormais dans un conteneur borné (`data-testid=offers-scroll`, `max-h-[72vh] overflow-y-auto`) ; affichage limité, le reste se déroule dans le conteneur.
- **Messagerie admin — scroll interne** : panneau Messages en hauteur relative au viewport (`h-[calc(100vh-11rem)]`) ; seul l'intérieur (liste de messages + liste de conversations) défile, header/input fixes.
- **Suppression de conversation** : nouveau `DELETE /api/chat/conversations/{candidate_id}` (admin) → supprime messages + doc conversation + marque les pièces jointes supprimées. Bouton corbeille (`conv-delete-<id>`) au survol de chaque conversation dans la liste admin. Testé 3/3 frontend.

## Implemented (2026-06, itération 24 — Refactoring frontend + recherche/sélection conversations + déploiement)
- **Refactoring frontend** : `AdminDashboard.js` (1548→1023 lignes) — extraction de `Candidates`, `Messages`, `Interviews` dans `/src/pages/admin/AdminCandidates.jsx`, `AdminMessages.jsx`, `AdminInterviews.jsx`. Comportement identique. Testé frontend 100 %.
- **Recherche conversations (admin)** : barre `conv-search-input` filtrant par nom de candidat / dernier message.
- **Sélection multiple** : mode `select-mode-toggle` avec cases par conversation → **Archiver** (désactiver en masse) ou **Supprimer** (en masse) + Annuler. Boucle sur `DELETE /chat/conversations/{id}` et `PUT .../active`.
- **Déploiement** : contrôle de readiness PASS. Corrigé `.gitignore` (les `.env` sont désormais versionnables). Redirection Google `/dashboard#session_id=` confirmée correcte (callback géré par le hash).

## Implemented (2026-06, itération 25 — Messagerie responsive)
- **Admin Messages responsive** (`AdminMessages.jsx`) : filtre par défaut = **Actives**. Sur téléphone, clic sur une discussion → la liste disparaît et une bande horizontale de profils (avatars + points de présence, `mobile-conv-strip`) apparaît en haut avec un bouton retour (`mobile-back-btn`). Desktop inchangé (2 colonnes).
- **ChatWidget candidat responsive** (`ChatWidget.js`) : sur **téléphone** le chat s'ouvre en plein écran (90vh hauteur, 100% largeur, ancré en bas) avec bouton **retour** (`chat-back-btn`) ; sur **ordinateur/tablette** (`sm:`) boîte flottante en bas à droite avec bouton **fermer** (`chat-close-btn`). Le bouton flottant est masqué sur mobile quand le chat est ouvert. Valeurs desktop identiques à avant (aucune régression).

## Implemented (2026-06, itération 26 — CV candidat, entretiens, hamburger, œil)
- **Menu hamburger (Navbar)** : sur mobile, un bouton hamburger regroupe désormais Connexion/Espace, Langue, Thème et Offres. Ordre : bouton **Admin/MySpace (ou Connexion) en haut**, puis Langue, thème, offres, et Déconnexion en bas. Desktop inchangé.
- **Activation via œil (Messages admin)** : le bouton Activer/Désactiver a été retiré de l'en-tête du chat et placé dans la **liste des conversations** sous forme d'icône **œil** (Eye/EyeOff) par ligne. Bug `toggleConvActive` corrigé.
- **CV candidat** : nouvel encart « CV / Curriculum Vitae » dans le profil candidat (ajout/modification). Backend `POST /api/profile/cv` (object storage) ; `public_user` expose `cv_file_id`/`cv_filename`.
- **Entretiens candidat** : bouton « Rejoindre » supprimé ; clic sur un entretien → panneau de détails (date, heure, lieu, notes, statut) + bouton **Supprimer** (`DELETE /api/interviews/me/{id}`).
- **Dashboard candidat** : bouton « Nouvelle candidature » retiré de la barre latérale.
- **Chat responsive** : ChatWidget plein écran + retour sur mobile / flottant + fermer sur desktop ; vue Messages admin ~90 % de l'écran, bouton retour placé en tête de la bande horizontale de profils.
- Vérifié frontend **100 % (5/5)** — testing agent iter 23. Aucun fichier corrompu.

## Implemented (2026-06, itération 27 — CV côté admin + correctifs code review)
- **CV dans le profil candidat (admin)** : `CandidateProfileDialog` affiche une carte « CV du candidat » avec lien « Voir le CV » (`profile-cv-card` / `profile-cv-btn`) quand `cv_file_id` existe. `GET /api/users/{id}` renvoie déjà `cv_file_id`/`cv_filename` via `public_user`.
- **Sécurité (code review #5)** : captcha et code de réinitialisation générés via `secrets` (aléa cryptographique) au lieu de `random`.
- **Clés React (code review #7)** : clés composites pour le marquee des catégories (Landing) et les puces (Chips) au lieu de l'index.
- Faux positifs écartés : les `is None`/`is not None` (code review #6) sont corrects ; `i18n.js` ne contient que des traductions (pas de secrets, #1) ; localStorage/httpOnly (#3) = choix d'archi Emergent conservé.

## ✅ Roadmap A→H terminée
Toutes les phases demandées (navigation/interactivité, appréciation, entretien à l'acceptation, notifications d'offres, appels vidéo+enregistrement+résumé IA, auth simplifiée, examen IA de pré-qualification, nettoyage auto, traduction complète FR/EN) sont livrées et testées.
