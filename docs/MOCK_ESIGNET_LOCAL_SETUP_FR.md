# Setup local mock eSignet (OIDC) pour AfyaID

Ce document permet de tester localement le flux d'identite sans credentials eSignet officiels, tout en gardant Firestore sur le projet cloud reel.

## 1) Architecture choisie

- Backend AfyaID FastAPI: local sur http://localhost:8000
- Mock IdP OIDC (Docker): local sur http://localhost:9000
- Firestore: cloud reel (projet `afya-id`)

Le mock IdP expose:
- `/.well-known/openid-configuration`
- `/.well-known/jwks.json`
- `/authorize`
- `/token`
- `/userinfo`

Il supporte:
- `private_key_jwt` (prioritaire)
- `client_secret_post` (fallback)

## 2) Fichiers ajoutes

- `docker-compose.mock-oidc.yml`
- `mock_idp/app.py`
- `mock_idp/bootstrap_keys.py`
- `mock_idp/Dockerfile`
- `mock_idp/requirements.txt`
- `mock_idp/users.json`
- `scripts/generate_mock_oidc_keys.py`

## 3) Utilisateurs mock

Credentials de test:

- Admin: `admin.mock / Admin123!`
- Doctor: `doctor.mock / Doctor123!`
- Health Worker: `healthworker.mock / Health123!`
- First Responder: `responder.mock / Responder123!`
- Patient verifie: `patient.verified / Patient123!`
- Patient pending: `patient.pending / Patient123!`

Claims inclus: `sub`, `email`, `name`, `phone_number`, `is_verified`, `nationalId`, `role`.

## 4) Variables d'environnement backend

Exemple minimum (voir `.env.example`):

```env
ESIGNET_BASE_URL=http://localhost:9000
CLIENT_ID=afya-local-client
CLIENT_SECRET=afya-local-secret
PRIVATE_KEY_PEM_PATH=./mock_idp/keys/client_private.pem
REDIRECT_URI=http://localhost:8000/auth/callback
JWT_AUDIENCE=

FIREBASE_PROJECT_ID=afya-id
FIREBASE_CREDENTIALS_JSON=./afya-id-firebase-adminsdk-fbsvc-2832f952d5.json
APP_ENV=development
ALLOW_FIREBASE_LOCAL_FALLBACK=true
```

## 5) Generation des cles RSA locales

Option recommandee (depuis la racine du projet):

```powershell
python scripts/generate_mock_oidc_keys.py
```

Fichiers generes:
- `mock_idp/keys/provider_private.pem` (signature des tokens du mock IdP)
- `mock_idp/keys/client_private.pem` (utilise par le backend pour `private_key_jwt`)

Si les fichiers n'existent pas, le conteneur mock peut aussi les creer au demarrage.

## 6) Demarrage local

1. Lancer le mock IdP:

```powershell
docker compose -f docker-compose.mock-oidc.yml up --build -d
```

2. Lancer le backend:

```powershell
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## 7) URLs locales

- Mock issuer: `http://localhost:9000`
- OIDC discovery: `http://localhost:9000/.well-known/openid-configuration`
- JWKS: `http://localhost:9000/.well-known/jwks.json`
- Authorize: `http://localhost:9000/authorize`
- Token: `http://localhost:9000/token`
- Userinfo: `http://localhost:9000/userinfo`
- Backend: `http://localhost:8000`

## 8) Test rapide bout en bout (navigateur)

1. Ouvrir:

```text
http://localhost:8000/auth/login?redirect=true
```

2. Le navigateur redirige vers `http://localhost:9000/authorize`.
3. Se connecter avec un user mock.
4. Le mock redirige vers `http://localhost:8000/auth/callback?code=...&state=...`.
5. Le backend echange le code, valide les tokens, recupere userinfo et cree/met a jour l'utilisateur dans Firestore.

## 9) Test API (curl)

1. Recuperer l'URL d'autorisation:

```bash
curl "http://localhost:8000/auth/login"
```

2. Utiliser ensuite le navigateur pour la partie login (formulaire mock).
3. Apres callback, recuperer `access_token` de la reponse et tester:

```bash
curl -H "Authorization: Bearer <ACCESS_TOKEN>" "http://localhost:8000/auth/me"
```

## 10) Verification patient (mock)

1. Authentifier un utilisateur HEALTH_WORKER mock.
2. Creer un patient via `POST /patients/register`.
3. Demarrer verification: `POST /patients/{patient_id}/verify/start`.
4. Ouvrir `authorization_url`, login mock.
5. Le callback met a jour `esignetSubjectId`, `identityStatus`, `kycStatus` du patient.

## 11) Migration future vers eSignet reel

Quand les credentials officiels seront disponibles:
- Remplacer `ESIGNET_BASE_URL` par l'issuer eSignet reel
- Remplacer `CLIENT_ID`, `CLIENT_SECRET` (ou cle production)
- Mettre `PRIVATE_KEY_PEM_PATH` sur la cle enregistree chez eSignet
- Verifier que `REDIRECT_URI` correspond exactement a celle enregistree

Le reste du flux backend (`/auth/login`, `/auth/callback`, `/auth/me`) est deja base sur OIDC discovery, donc la transition se limite surtout a la configuration.
