# Documentation API AfyaID

## 1. Introduction

Cette documentation est là pour la compréhension de ce qui a été fait dans l'API pour une meilleure  intégration dans Flutter.

l'API AfyaID est notre backend pour gérer l’authentification, les profils staff, les patients et le flux KYC.

En pratique, le backend fait trois choses principales :

1. authentifier les utilisateurs via eSignet,
2. stocker et lire les données métier dans Firebase Firestore,
3. protéger les accès selon le rôle de l’utilisateur.

Concrètement pour Flutter :

- l’application mobile appelle cette API,
- l’API lit/écrit dans Firebase,
- l’API parle à eSignet dès qu’on a les credentials réels.

## 2. Architecture

```mermaid
flowchart LR
    F[Flutter App] -->|HTTPS JSON| B[FastAPI / AfyaID]
    B -->|Firestore SDK| FS[(Firebase Firestore)]
    B -->|OIDC / OAuth2| ES[eSignet]
    ES -->|ID Token + Userinfo| B
```

### Lecture rapide

- Flutter envoie les requêtes à FastAPI.
- FastAPI lit et écrit dans Firestore.
- eSignet sert à l’authentification OIDC.
- En production, Firebase est réel.
- eSignet est encore en mode mock tant que les vrais `CLIENT_ID` et `CLIENT_SECRET` ne sont pas fournis.

## 3. Authentification

### Flux de connexion

```mermaid
sequenceDiagram
    participant U as Utilisateur Flutter
    participant A as AfyaID Backend
    participant E as eSignet
    participant F as Firestore

    U->>A: GET /auth/login
    A->>F: sauvegarde state + nonce
    A-->>U: authorization_url
    U->>E: ouverture de la page eSignet
    E-->>A: GET /auth/callback?code=...&state=...
    A->>F: vérifie state, nonce
    A->>E: échange du code contre des tokens
    E-->>A: access_token + id_token
    A->>E: lecture userinfo
    A->>F: crée ou met à jour le user
    A-->>U: profil + tokens + statut KYC
```

### Ce qui est déjà réel maintenant 

- la validation Firebase,
- la création et la lecture des utilisateurs,
- la gestion du state et du nonce,
- la logique de rôle et de KYC,
- les routes patients.

### Ce qui dépend encore de eSignet réel

- l’échange réel du code OAuth,
- la validation réelle d’un `id_token` de production,
- la lecture réelle de `userinfo`,
- la vérification réelle de l’identité patient.

## 4. Rôles et permissions

### Admin

- peut assigner un rôle à un staff,
- peut valider ou rejeter un KYC,
- peut lire les vues patients,
- peut lire la liste des KYC en attente.

### Doctor

- peut lire le dossier complet du patient,
- peut lire le résumé médical.

### Health Worker

- peut créer un patient,
- peut mettre à jour un patient,
- peut lancer une vérification eSignet patient,
- peut lire un patient complet.

### First Responder

- peut lire uniquement la vue d’urgence du patient,
- ne voit pas le dossier complet.

## 5. Patient Flow

```mermaid
flowchart TD
    A[Health Worker] --> B[POST /patients/register]
    B --> C{Identité eSignet ?}
    C -->|Oui| D[Statut identityStatus=VERIFIED]
    C -->|Non| E[Statut identityStatus=PENDING]
  A --> F[PATCH /patients/:patient_id]
  A --> G[POST /patients/:patient_id/verify/start]
    G --> H[Retour vers eSignet]
    H --> I[GET /auth/callback]
    I --> J[Mise à jour patient Firestore]
    J --> K[Admin/Doctor/First Responder lisent les vues adaptées]
```

### Résumé fonctionnel

- `register` crée le patient.
- `update` modifie le patient.
- `verify/start` lance la vérification eSignet.
- `/summary` donne la vue médicale pour le doctor.
- `/emergency` donne la vue courte pour le first responder.

## 6. Base URL de production

URL de l'API en production :

`https://afya-id-419586439350.europe-west2.run.app`

Tous les endpoints documentés ici utilisent cette base URL.

## 7. Authentification des requêtes

Les routes protégées utilisent `Authorization: Bearer <token>`.

Exemple :

```http
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

## 8. Endpoints

### 8.1 Santé

#### GET /

Description : vérifie que l’API répond.

Réponse exemple :

```json
{
  "status": "healthy",
  "service": "AfyaId Backend",
  "version": "1.0.0",
  "provider": "eSignet (MOSIP)",
  "docs": "/docs"
}
```

#### GET /health

Description : retourne l’état de configuration.

Réponse exemple :

```json
{
  "status": "healthy",
  "esignet_base_url": "https://esignet-mock.collab.mosip.net",
  "client_id_configured": false,
  "firebase_configured": true,
  "private_key_configured": false
}
```

### 8.2 Authentification

#### GET /auth/login

Rôle requis : aucun, mais c’est le point d’entrée de login.

Description : génère l’URL eSignet, sauvegarde `state` et `nonce`.

Réponse exemple :

```json
{
  "authorization_url": "https://...",
  "state": "f2d1..."
}
```

#### GET /auth/callback

Rôle requis : aucun, appelé par eSignet.

Query params :

- `code` obligatoire
- `state` obligatoire
- `error` optionnel
- `error_description` optionnel

Réponse exemple staff :

```json
{
  "access_token": "...",
  "id_token": "...",
  "token_type": "Bearer",
  "user": {
    "uid": "sub-123",
    "email": "name@gmail.com",
    "fullName": "Abraham Faith",
    "role": "DOCTOR",
    "kycStatus": "VERIFIED_BY_PROVIDER"
  },
  "kyc_status": "VERIFIED_BY_PROVIDER",
  "profile_complete": false,
  "message": "Identity verified by provider. Please complete your profile (hospital, role, matriculeNumber)."
}
```

#### GET /auth/me

Rôle requis : utilisateur authentifié.

Description : retourne le profil courant.

Réponse exemple :

```json
{
  "user": {
    "uid": "sub-123",
    "email": "name@gmail.com",
    "fullName": "Abraham Imani",
    "role": "DOCTOR"
  },
  "kyc_status": "VERIFIED_BY_PROVIDER",
  "profile_complete": true
}
```

#### POST /auth/complete-profile

Rôle requis : utilisateur authentifié.

Description : complète le profil d’un utilisateur déjà vérifié par eSignet.

Body exemple :

```json
{
  "hospital": "HGR Bukavu",
  "role": "DOCTOR",
  "matriculeNumber": "MED-001",
  "title": "Dr"
}
```

Réponse exemple :

```json
{
  "message": "Profile completed successfully.",
  "user": { "uid": "sub-123" },
  "profile_complete": true
}
```

### 8.3 KYC

#### POST /kyc/submit

Rôle requis : utilisateur authentifié.

Description : soumet les données KYC quand le provider n’a pas déjà vérifié l’identité.

Body exemple :

```json
{
  "nationalId": "123456789",
  "hospital": "HGR Bukavu",
  "role": "HEALTH_WORKER",
  "title": "Mr",
  "matriculeNumber": "HW-1001",
  "specialty": "General Care",
  "unitName": "Ward A",
  "contactPhone": "+243000000000",
  "documentUrl": "https://..."
}
```

Réponse exemple :

```json
{
  "message": "KYC documents submitted successfully. Awaiting verification.",
  "kycStatus": "SUBMITTED",
  "user": { "uid": "sub-123" }
}
```

### 8.4 Users

#### PATCH /users/me/profile

Rôle requis : utilisateur authentifié.

Description : met à jour le profil courant, mais ne permet pas le changement de rôle.

Body exemple :

```json
{
  "fullName": "Abraham Faith",
  "hospital": "HGR Bukavu",
  "matriculeNumber": "MED-001",
  "contactPhone": "+243000000000"
}
```

Réponse exemple :

```json
{
  "message": "Profile updated successfully.",
  "user": { "uid": "sub-123" },
  "profile_complete": true
}
```

### 8.5 Patients

#### POST /patients/register

Rôle requis : `HEALTH_WORKER` ou `ADMIN`.

Description : crée un patient.

Body exemple :

```json
{
  "fullName": "Marie M.",
  "dateOfBirth": "1990-02-14",
  "gender": "F",
  "phoneNumber": "+243000000001",
  "nationalId": "NAT-001",
  "emergencyContact": "Cimanuka Kobojo +243000000002",
  "bloodType": "O+",
  "allergies": ["Penicillin"],
  "chronicConditions": ["Hypertension"],
  "medications": ["Aspirin"],
  "hospital": "HGR Bukavu",
  "esignetSubjectId": "sub-123",
  "identityVerified": true
}
```

Réponse exemple :

```json
{
  "message": "Patient registered successfully.",
  "patient": {
    "patientId": "PAT-123456789abc",
    "fullName": "Marie M.",
    "identityStatus": "VERIFIED",
    "kycStatus": "VERIFIED_BY_PROVIDER"
  },
  "identity_status": "VERIFIED",
  "kyc_status": "VERIFIED_BY_PROVIDER"
}
```

#### PATCH /patients/{patient_id}

Rôle requis : `HEALTH_WORKER` ou `ADMIN`.

Description : met à jour un patient.

Body exemple :

```json
{
  "phoneNumber": "+243000000003",
  "bloodType": "A+",
  "allergies": ["Dust"]
}
```

Réponse exemple :

```json
{
  "message": "Patient updated successfully.",
  "patient": { "patientId": "PAT-123456789abc" }
}
```

#### GET /patients/{patient_id}

Rôle requis : `HEALTH_WORKER`, `DOCTOR`, `ADMIN`.

Description : retourne le dossier complet.

Réponse exemple :

```json
{
  "patient": {
    "patientId": "PAT-123456789abc",
    "fullName": "Marie M.",
    "dateOfBirth": "1990-02-14",
    "gender": "F",
    "phoneNumber": "+243000000001",
    "nationalId": "NAT-001",
    "emergencyContact": "Cimanuka Kobojo +243000000002",
    "bloodType": "O+",
    "allergies": ["Penicillin"],
    "chronicConditions": ["Hypertension"],
    "medications": ["Aspirin"],
    "hospital": "HGR Bukavu",
    "registeredBy": "sub-123",
    "registrationSource": "esignet",
    "identityStatus": "VERIFIED",
    "kycStatus": "VERIFIED_BY_PROVIDER",
    "createdAt": "2026-04-02T11:00:00",
    "updatedAt": "2026-04-02T11:05:00",
    "isActive": true
  },
  "accessed_by": "sub-999",
  "access_role": "DOCTOR"
}
```

#### GET /patients/{patient_id}/summary

Rôle requis : `DOCTOR` ou `ADMIN`.

Description : vue médicale simplifiée.

Réponse exemple :

```json
{
  "patientId": "PAT-123456789abc",
  "fullName": "Marie M.",
  "dateOfBirth": "1990-02-14",
  "gender": "F",
  "bloodType": "O+",
  "allergies": ["Penicillin"],
  "chronicConditions": ["Hypertension"],
  "medications": ["Aspirin"],
  "emergencyContact": "Paul M. +243000000002",
  "hospital": "HGR Bukavu",
  "identityStatus": "VERIFIED",
  "isActive": true
}
```

#### GET /patients/{patient_id}/emergency

Rôle requis : `FIRST_RESPONDER` ou `ADMIN`.

Description : vue d’urgence minimale.

Réponse exemple :

```json
{
  "patientId": "PAT-123456789abc",
  "fullName": "Marie M.",
  "bloodType": "O+",
  "allergies": ["Penicillin"],
  "chronicConditions": ["Hypertension"],
  "emergencyContact": "Paul M. +243000000002"
}
```

#### POST /patients/{patient_id}/verify/start

Rôle requis : `HEALTH_WORKER` ou `ADMIN`.

Description : lance la vérification d’identité eSignet pour un patient existant.

Réponse exemple :

```json
{
  "message": "Patient verification initiated.",
  "patientId": "PAT-123456789abc",
  "authorization_url": "https://...",
  "state": "abc123"
}
```

### 8.6 Admin

#### POST /admin/users/{uid}/role

Rôle requis : `ADMIN`.

Body exemple :

```json
{
  "role": "DOCTOR"
}
```

Réponse exemple :

```json
{
  "message": "Role assigned successfully.",
  "user": { "uid": "sub-123", "role": "DOCTOR" }
}
```

#### POST /admin/users/{uid}/kyc/verify

Rôle requis : `ADMIN`.

Body exemple :

```json
{
  "notes": "Checked manually and approved."
}
```

#### POST /admin/users/{uid}/kyc/reject

Rôle requis : `ADMIN`.

Body exemple :

```json
{
  "reason": "Document mismatch"
}
```

#### GET /admin/kyc/pending

Rôle requis : `ADMIN`.

Réponse exemple :

```json
{
  "count": 1,
  "items": [],
  "reviewer": "admin-sub"
}
```

## 9. Format des données patient

### Format retourné par l’API

Le backend expose un objet patient avec cette structure logique :

```json
{
  "patientId": "string",
  "esignetSubjectId": "string | null",
  "fullName": "string",
  "dateOfBirth": "string | null",
  "gender": "string | null",
  "phoneNumber": "string | null",
  "nationalId": "string | null",
  "emergencyContact": "string | null",
  "bloodType": "string | null",
  "allergies": ["string"],
  "chronicConditions": ["string"],
  "medications": ["string"],
  "hospital": "string | null",
  "registeredBy": "string | null",
  "registrationSource": "manual | esignet",
  "identityStatus": "PENDING | VERIFIED | REJECTED",
  "kycStatus": "PENDING | VERIFIED_BY_PROVIDER | VERIFIED | REJECTED",
  "createdAt": "string | null",
  "updatedAt": "string | null",
  "isActive": true
}
```

### Important pour Flutter

- Les tableaux `allergies`, `chronicConditions` et `medications` doivent être lus comme des listes de chaînes.
- Les champs `phoneNumber`, `bloodType`,... peuvent être absents si le patient n’a pas ces données pour renforcer le KYC on pourra tester la vérification de OTP du numéro téléphone.
- Les anciennes données Firestore peuvent contenir des noms legacy (`phone`, `bloodGroup`, `medAllergies`, `activeMedecines`).
- Le backend doit normaliser ces cas avant exposition à Flutter si vous gardez ces anciens documents.

## 10. Gestion des erreurs

### Erreurs courantes

- `400 Bad Request` : état invalide, code OAuth invalide, body incomplet.
- `401 Unauthorized` : token manquant ou invalide.
- `403 Forbidden` : rôle non autorisé.
- `404 Not Found` : patient ou user introuvable.
- `409 Conflict` : nationalId ou eSignet déjà utilisé.
- `500 Internal Server Error` : erreur serveur ou dépendance externe indisponible.

### Exemples

```json
{
  "detail": "Invalid or expired state parameter."
}
```

```json
{
  "detail": "This National ID is already registered to another patient."
}
```

## 11. Local vs Production

### Ce qui est réel en production maintenant comme rappel

- Firebase Firestore,
- création/lecture/mise à jour/suppression des patients,
- création et lecture des utilisateurs staff,
- RBAC,
- KYC,
- validation des routes protégées.

### Ce qui reste mock tant que nous attendons les credentials ou identifiants du projet en eSignet

- `GET /auth/login`,
- `GET /auth/callback`,
- `POST /patients/{patient_id}/verify/start`,
- la branche de vérification d’identité patient dans le callback.

## 12. Déploiement Cloud Run

### Image Docker

Le backend est prévu pour tourner sur Cloud Run avec Uvicorn.

### Variables d’environnement à définir dans Cloud Run

Obligatoires :

- `APP_ENV=production`
- `ALLOW_FIREBASE_LOCAL_FALLBACK=false`
- `FIREBASE_PROJECT_ID=afya-id`
- `ESIGNET_BASE_URL=https://esignet-mock.collab.mosip.net`
- `CLIENT_ID=...`
- `CLIENT_SECRET=...`
- `REDIRECT_URI=https://afya-id-419586439350.europe-west2.run.app/auth/callback`
- `APP_BASE_URL=https://afya-id-419586439350.europe-west2.run.app`
- `FRONTEND_URL=https://afya-id.web.app`
- `ALLOWED_ORIGINS=https://afya-id.web.app,https://afya-id-419586439350.europe-west2.run.app`
- `APP_SECRET_KEY=...`

Remarque importante :

- sur Cloud Run, `FIREBASE_CREDENTIALS_JSON` n’est pas obligatoire dans notre setup actuel,
- le service utilise les Application Default Credentials du runtime (compte de service Cloud Run).
- on déploie le service sur le projet GCP `afyaid-backend1`, mais les données Firestore sont dans le projet `afya-id`.

### Commandes de déploiement recommandées

```bash
gcloud builds submit --tag europe-west2-docker.pkg.dev/afyaid-backend1/afyaid/afyaid-backend:1.0.0
gcloud run deploy afya-id \
  --image europe-west2-docker.pkg.dev/afyaid-backend1/afyaid/afyaid-backend:1.0.0 \
  --region europe-west2 \
  --platform managed \
  --allow-unauthenticated \
  --set-env-vars APP_ENV=production,ALLOW_FIREBASE_LOCAL_FALLBACK=false,FIREBASE_PROJECT_ID=afya-id,ESIGNET_BASE_URL=https://esignet-mock.collab.mosip.net,APP_BASE_URL=https://afya-id-419586439350.europe-west2.run.app,REDIRECT_URI=https://afya-id-419586439350.europe-west2.run.app/auth/callback,FRONTEND_URL=https://afya-id.web.app,ALLOWED_ORIGINS=https://afya-id.web.app,https://afya-id-419586439350.europe-west2.run.app
```

### Vérification rapide après déploiement

```bash
curl https://afya-id-419586439350.europe-west2.run.app/
curl https://afya-id-419586439350.europe-west2.run.app/health
```

## 13. Points à valider quand eSignet réel est prêt

1. login réel avec `CLIENT_ID` / `CLIENT_SECRET`,
2. callback réel avec `code` et `state`,
3. validation réelle du `id_token`,
4. création staff après login,
5. vérification patient via `verify/start`,
6. lecture réelle de `userinfo`,
7. test d’erreurs eSignet.

## 14. Résumé final

- Firebase marche.
- Le fallback local est désactivé pour cette api en production.
- Les routes patient sont prêtes pour Flutter.
- eSignet attend encore les vrais identifiants pour être validé.