# Plan de test API AfyaID (verification complete avant validation Flutter)

Ce document est le plan de test terrain pour verifier que tous les endpoints fonctionnent bien, surtout ceux avec Authorization Bearer.

## 1) Objectif

Valider de ton cote, pas a pas:

- que les endpoints publics repondent correctement,
- que la securite Bearer bloque bien les acces non autorises,
- que les endpoints proteges fonctionnent bien avec un token valide,
- que les restrictions de role sont correctes (ADMIN, DOCTOR, HEALTH_WORKER, FIRST_RESPONDER),
- que Firebase est bien utilise (et pas un fallback local cache).

## 2) Informations de test

Base API de production:

- https://afya-id-419586439350.europe-west2.run.app

Liens utiles:

- Swagger: https://afya-id-419586439350.europe-west2.run.app/docs
- OpenAPI JSON: https://afya-id-419586439350.europe-west2.run.app/openapi.json

## 3) Prerequis avant de commencer

1. Avoir curl ou Postman.
2. Avoir au moins 1 token Bearer valide (meme si eSignet est encore mock, des tokens de test peuvent venir de votre environnement).
3. Idealement avoir 4 tokens differents:
   - token ADMIN
   - token HEALTH_WORKER
   - token DOCTOR
   - token FIRST_RESPONDER
4. Si tu n as pas encore ces 4 roles, commence avec un token ADMIN puis attribue les roles avec les endpoints admin.

## 4) Variables de travail conseillees (PowerShell)

Commande a adapter sur ta machine:

- $BASE = "https://afya-id-419586439350.europe-west2.run.app"
- $TOKEN_ADMIN = "met_un_vrai_token_admin"
- $TOKEN_HW = "met_un_vrai_token_health_worker"
- $TOKEN_DOCTOR = "met_un_vrai_token_doctor"
- $TOKEN_FR = "met_un_vrai_token_first_responder"

## 5) Etape A - Smoke test endpoints publics

Action 1:

- GET / 
- attendu: 200 et version 1.0.0

Action 2:

- GET /health
- attendu: 200

Action 3:

- GET /docs
- attendu: 200

Action 4:

- GET /openapi.json
- attendu: 200

Action 5:

- GET /auth/login
- attendu: 200 avec authorization_url et state
- ce test est important car il confirme que la sauvegarde du state en Firestore fonctionne

## 6) Etape B - Verification securite Bearer (obligatoire)

Pour chaque endpoint protege, faire ces 2 tests avant le test positif:

Test securite 1 (sans token):

- attendu: 401

Test securite 2 (token invalide):

- attendu: 401

Ensuite seulement, faire le test avec token valide.

## 7) Etape C - Verification des endpoints utilisateur

### C1) GET /auth/me

- avec token valide (n importe quel role authentifie)
- attendu: 200 et user retourne

### C2) PATCH /users/me/profile

- avec token valide
- body minimal recommande:
  - fullName
  - hospital
  - contactPhone
- attendu: 200

Test negatif critique:

- envoyer role dans le body
- attendu: 403 (role changes are restricted)

### C3) POST /kyc/submit

- avec token valide
- body exemple:
  - nationalId
  - hospital
  - role
  - matriculeNumber
- attendu: 200 et kycStatus SUBMITTED

Test negatif:

- nationalId deja utilise
- attendu: 409

## 8) Etape D - Preparation des roles (si necessaire)

Si tu as seulement un token ADMIN au depart:

1. Creer ou identifier 3 users cibles (doctor, health worker, first responder).
2. ADMIN appelle:
   - POST /admin/users/{uid}/role pour DOCTOR
   - POST /admin/users/{uid}/role pour HEALTH_WORKER
   - POST /admin/users/{uid}/role pour FIRST_RESPONDER
3. Verifier ensuite avec leurs tokens respectifs.

## 9) Etape E - Patient flow complet (le plus important)

### E1) POST /patients/register

- role: HEALTH_WORKER ou ADMIN
- attendu: 201
- garder patientId retourne (important pour la suite)

### E2) PATCH /patients/{patient_id}

- role: HEALTH_WORKER ou ADMIN
- attendu: 200

### E3) GET /patients/{patient_id}

- roles autorises: HEALTH_WORKER, DOCTOR, ADMIN
- attendu: 200

Test negatif:

- avec token FIRST_RESPONDER
- attendu: 403

### E4) GET /patients/{patient_id}/summary

- roles autorises: DOCTOR, ADMIN
- attendu: 200

Test negatif:

- avec token HEALTH_WORKER
- attendu: 403

### E5) GET /patients/{patient_id}/emergency

- roles autorises: FIRST_RESPONDER, DOCTOR, ADMIN
- attendu: 200

Test negatif:

- sans token
- attendu: 401

### E6) POST /patients/{patient_id}/verify/start

- roles autorises: HEALTH_WORKER, ADMIN
- attendu: 200 avec authorization_url et state

## 10) Etape F - Endpoints admin

### F1) GET /admin/kyc/pending

- role: ADMIN
- attendu: 200

### F2) POST /admin/users/{uid}/role

- role: ADMIN
- attendu: 200

### F3) POST /admin/users/{uid}/kyc/verify

- role: ADMIN
- attendu: 200

### F4) POST /admin/users/{uid}/kyc/reject

- role: ADMIN
- attendu: 200

Test negatif global admin:

- refaire chaque endpoint admin avec token non ADMIN
- attendu: 403

## 11) Verification Firebase reel

Fais ces controles pendant les tests:

1. /auth/login ne doit plus renvoyer erreur database default does not exist.
2. Les creations patient sont visibles dans Firestore projet afya-id.
3. Les updates profile et KYC apparaissent bien dans les collections users/patients.

Si 1, 2, 3 sont vrais, alors backend branche correctement sur Firebase reel.

## 12) Definition de Pret a partager a Flutter

Tu peux confirmer a l equipe Flutter que c est OK quand:

1. Tous les tests publics sont verts.
2. Tous les tests securite 401 et 403 sont verts.
3. Tous les tests positifs des endpoints proteges sont verts avec tokens valides.
4. Patient flow complet E1 a E6 est vert.
5. Les donnees apparaissent dans Firestore projet afya-id.

## 13) Checklist finale rapide

- [ ] GET / OK
- [ ] GET /health OK
- [ ] GET /auth/login OK
- [ ] securite 401 sans token verifiee
- [ ] securite 401 token invalide verifiee
- [ ] securite 403 role incorrect verifiee
- [ ] patients/register OK
- [ ] patients/{id} OK
- [ ] patients/{id}/summary OK
- [ ] patients/{id}/emergency OK
- [ ] admin endpoints OK
- [ ] donnees visibles dans Firestore afya-id
