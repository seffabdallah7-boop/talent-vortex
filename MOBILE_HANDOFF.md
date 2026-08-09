# Talent Vortex — Handoff pour l'agent MOBILE (React Native / Expo)

> Colle ce document au DÉBUT de ta conversation avec l'agent « Mobile » d'Emergent.
> L'app mobile NE recrée PAS le backend : elle consomme le MÊME backend FastAPI déjà déployé,
> donc MÊMES données, MÊMES modèles, synchronisation temps réel avec le web.

## 0. Objectif
Créer une app mobile Expo (React Native) reprenant TOUTES les fonctionnalités du web :
auth (email+captcha+OTP, Google), offres, candidatures (CV + message vocal), suivi de statut,
chat candidat↔admin, assistant IA, entretiens (visio), notifications, profil candidat,
et tableau de bord admin (offres, candidatures, contrats, entretiens, utilisateurs).

## 1. Connexion au backend
- Base URL = URL du backend DÉPLOYÉ. Tous les endpoints sont préfixés `/api`.
- Auth = header `Authorization: Bearer <token>`. Le token vient de login (verify-otp) ou register ou Google.
- Stocke le token dans un stockage sécurisé (expo-secure-store).

## 2. Flux d'authentification (IMPORTANT)
1. `GET /api/auth/captcha` → { captcha_id, question ex "3 + 5" }. La réponse = somme.
2. Inscription : `POST /api/auth/register` { name, email, password, captcha_id, captcha_answer } → { token, user } (pas d'OTP à l'inscription).
3. Connexion : `POST /api/auth/login` { email, password, captcha_id, captcha_answer } → { otp_required:true, email }.
4. `POST /api/auth/verify-otp` { email, code } → { token, user }. (OTP envoyé par email ; en dev il est aussi dans les logs backend.)
5. Mot de passe oublié : `POST /api/auth/forgot-password` { email, captcha_id, captcha_answer } → puis `POST /api/auth/reset-password` { email, code, new_password }.
6. Google : ouvrir le flux OAuth Emergent puis `POST /api/auth/google/session` { session_id } → { token, user }.
7. `GET /api/auth/me` → profil courant. `role` = "admin" | "candidate" (route l'app en conséquence).
- Mot de passe : min 8 caractères, 1 lettre + 1 chiffre. Blocage après 5 échecs (15 min).

## 3. Endpoints (tous préfixés /api)
AUTH: POST /auth/register, POST /auth/login, POST /auth/verify-otp, GET /auth/captcha,
POST /auth/forgot-password, POST /auth/reset-password, POST /auth/google/session, GET /auth/me
PROFIL: GET /profile, PUT /profile
OFFRES: GET /jobs?q= (public ; si Bearer candidat → champs match_score/match_percent + tri par pertinence),
GET /jobs/all (admin, +applicants/+pending), GET /jobs/{id}, POST /jobs (admin), POST /jobs/ai-draft (admin),
PUT /jobs/{id} (admin), PUT /jobs/{id}/active (admin), DELETE /jobs/{id} (admin)
CANDIDATURES: POST /applications (multipart: job_id, cover_note, cv[fichier], voice[fichier optionnel]),
GET /applications/me, GET /applications?status=&job_id= (admin), PUT /applications/{id}/status (admin, {status: pending|accepted|rejected}),
PUT /applications/{id}/review (admin, {admin_note, rating 1..5}), DELETE /applications/{id} (admin)
CONTRATS: GET /contracts/me, GET /contracts?status= (admin), POST/PUT/DELETE /contracts (admin)
FICHIERS: GET /files/{file_id} (auth ; renvoie le binaire CV/audio ; accepte aussi ?auth=<token> en query)
UTILISATEURS (admin): GET /candidates, GET /users?q=, GET /admin/nationalities,
PUT /users/{id}/role ({role: admin|candidate}), DELETE /users/{id}, DELETE /candidates/{id}
PRÉSENCE: POST /presence/ping (toutes les 30s), GET /presence/admin
CHAT: GET /chat/conversations (admin), GET /chat/messages?candidate_id= , POST /chat/messages ({text, candidate_id?})
  (polling toutes ~4s ; read=true quand l'interlocuteur ouvre la conversation)
IA: POST /ai/chat ({session_id, message}) → {reply}, GET /ai/history?session_id=
THÈME: GET /settings/theme, PUT /settings/theme (admin)
STATS: GET /admin/stats (admin)
ENTRETIENS: GET /interviews (admin), GET /interviews/me, POST /interviews (admin),
PUT /interviews/{id} (admin), DELETE /interviews/{id} (admin)
EXPORT CSV: GET /export/applications, GET /export/contracts (admin)
NOTIFICATIONS: GET /notifications → {items, unread}, POST /notifications/read-all
VISIO: salle Jitsi = `https://meet.jit.si/recrutai-itw-<interview_id>` (utiliser WebView ou lien).

## 4. Modèles de données (collections MongoDB)
users: user_id, email, name, role(admin|candidate), password_hash(privé), auth_provider(email|google),
  picture, created_at, phone, nationality, city, country, domains[], tools[], years_experience,
  current_position, headline, bio, ai_domains[], profile_completed, last_seen
jobs: id, title, company, location, type, category, description, requirements, salary, is_active, created_at
  (Réponse candidat enrichie : match_score, match_percent)
applications: id, job_id, job_title, candidate_id, candidate_name, candidate_email, cv_file_id, cv_filename,
  voice_file_id, transcription, cover_note, status(pending|accepted|rejected), admin_note, rating(1..5), created_at, updated_at
files: id, storage_path, original_filename, content_type, owner_id, is_deleted, created_at
messages: id, conversation_id(=candidate_id), candidate_name, sender_id, sender_role(admin|candidate), text, read, created_at
notifications: id, user_id, type(status|message|interview|application), title, body, read, created_at, [interview_id]
contracts: id, title, client, candidate_id, candidate_name, job_title, amount, start_date, end_date, status(en_cours|boucle|resilie), notes, created_at
interviews: id, title, candidate_id, candidate_name, application_id, date(YYYY-MM-DD), time(HH:MM), location, notes, status, created_at
settings: key="theme", primary, primary_foreground, name
ai_messages: session_id, role(user|assistant), text, created_at

## 5. Champs de profil candidat (PUT /profile)
name, phone, nationality, city, country, domains[], tools[], years_experience, current_position, headline, bio
→ profile_completed = true si name+phone+nationality+domains présents. L'IA remplit ai_domains (matching des offres).

## 6. Notes techniques
- Langue par défaut FR (web bilingue FR/EN via i18n ; à reproduire côté mobile si souhaité).
- Upload CV/vocal : multipart/form-data. Vocal ≤ 10 min ; transcription auto (Whisper) côté serveur.
- Rappel entretien 5 min avant : à recalculer côté client mobile à partir de date+time.
- NE PAS coder d'URL en dur : mettre la base URL du backend dans la config Expo.
