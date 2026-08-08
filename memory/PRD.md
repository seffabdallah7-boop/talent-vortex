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

## Backlog
- P1: Enregistrement/upload vocal E2E automatisé (testé manuellement seulement) ; limite de taille des uploads.
- P1: Chat temps réel (WebSocket) au lieu du polling.
- P2: Notifications email (candidature reçue / statut changé) via Resend.
- P2: Filtres/recherche avancés côté admin ; pagination.
- P2: App React Native (mobile).
- P2: Rate-limiting sur /api/ai/chat.

## Next Tasks
- Selon retour utilisateur.
