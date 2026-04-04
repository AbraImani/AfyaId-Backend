# Guide Flutter - Utilisation Backend AfyaID en mode local/mock

Date de validation: 2026-04-04

## 1) Realite du setup actuel: ce qui est reel vs mock

- Firebase/Firestore: reel (projet cloud afya-id).
- Backend FastAPI AfyaID: reel (code production), executable en local et aussi deploye sur Cloud Run.
- eSignet officiel: non branche en credentials officiels dans ce setup.
- Provider d'identite mock OIDC: local (localhost:9000) pour les tests developpement.

En clair: la persistence des donnees est reelle, mais le fournisseur d'identite utilise pour tests locaux est simule.

## 2) URLs Flutter a utiliser

### Mode local/mock (recommande pour integration immediate)

- Backend API (machine dev): http://localhost:8000
- Mock OIDC/eSignet local: http://localhost:9000

### Mode public/deploye

- Backend API public: https://afya-id-419586439350.europe-west2.run.app

Important:
- Le backend public repond bien.
- Le flux auth public ne doit pas etre considere "pret equipe" tant qu'un vrai client OIDC valide est configure cote deploiement (voir section limitations).

## 3) Prerequis et lancement backend local

Prerequis:
- Python 3.10+
- venv cree
- Dependances installees: pip install -r requirements.txt
- Fichier .env local configure (voir .env.example)

Variables minimales backend local:
- ESIGNET_BASE_URL=http://localhost:9000
- CLIENT_ID=afya-local-client
- CLIENT_SECRET=afya-local-secret
- PRIVATE_KEY_PEM_PATH=./mock_idp/keys/client_private.pem
- REDIRECT_URI=http://localhost:8000/auth/callback
- FIREBASE_PROJECT_ID=afya-id
- FIREBASE_CREDENTIALS_JSON=./afya-id-firebase-adminsdk-fbsvc-2832f952d5.json
- APP_ENV=development

Commande:

uvicorn main:app --host 0.0.0.0 --port 8000 --reload

Verification rapide:
- GET http://localhost:8000/
- GET http://localhost:8000/health

## 4) Lancement du mock identity provider local

### Option A - Docker (recommandee)

1. Generer les cles:

python scripts/generate_mock_oidc_keys.py

2. Demarrer le mock:

docker compose -f docker-compose.mock-oidc.yml up --build -d

3. Verifier:
- GET http://localhost:9000/.well-known/openid-configuration
- GET http://localhost:9000/.well-known/jwks.json

### Option B - Direct local (si Docker indisponible)

1. Generer les cles:

python scripts/generate_mock_oidc_keys.py

2. Installer les dependances mock:

pip install -r mock_idp/requirements.txt

3. Lancer le mock IdP:

uvicorn mock_idp.app:app --host 0.0.0.0 --port 9000 --reload

## 5) Comment Flutter doit se connecter a localhost

### Android Emulator

- Utiliser http://10.0.2.2:8000 pour joindre le backend local sur la machine host.
- Pour le provider mock, utiliser http://10.0.2.2:9000 si l'appli ouvre les URLs via l'emulateur.

### Appareil Android physique

- Utiliser l'IP LAN de la machine dev, ex: http://192.168.1.20:8000
- Idem pour mock OIDC: http://192.168.1.20:9000
- Le mobile et la machine dev doivent etre sur le meme reseau.
- Autoriser le firewall local pour ports 8000 et 9000.

### Flutter Web

- Utiliser directement http://localhost:8000
- Le navigateur ouvrira la page login du mock sur http://localhost:9000

## 6) Flux d'authentification en mode local

1. Flutter appelle GET /auth/login.
2. Backend renvoie authorization_url + state.
3. Flutter ouvre authorization_url (WebView ou navigateur externe).
4. Utilisateur se connecte sur le mock IdP.
5. Mock redirige vers backend /auth/callback avec code + state.
6. Backend echange le code, valide les tokens, recupere userinfo, cree/met a jour user Firestore.
7. Backend renvoie access_token et user.
8. Flutter stocke access_token.
9. Flutter appelle GET /auth/me avec Authorization: Bearer <token> pour recuperer le profil.

Note implementation Flutter:
- Si Flutter pilote le navigateur externe, ecouter la redirection finale vers /auth/callback et recuperer la reponse JSON.
- Alternative pratique: ouvrir /auth/login?redirect=true dans navigateur puis traiter le resultat callback selon votre strategy deep-link/webview.

## 7) Flux patient a tester cote Flutter

1. Auth staff (doctor/health worker/admin mock).
2. Creation patient: POST /patients/register.
3. Mise a jour patient: PUT /patients/{patient_id}.
4. Consultation resume: GET /patients/{patient_id}/summary.
5. Vue urgence: GET /patients/{patient_id}/emergency.
6. Verification identite mock:
   - POST /patients/{patient_id}/verify/start
   - Ouvrir authorization_url
   - Login mock
   - Callback backend met a jour identityStatus, kycStatus, esignetSubjectId.

## 8) Exemples concrets requetes/reponses

### Login bootstrap

Requete:
- GET /auth/login

Reponse attendue (extrait):

{
  "authorization_url": "http://localhost:9000/authorize?...",
  "state": "d29aa392cd874a53ab0eb2b2a8516ad3"
}

### Callback succes

Requete:
- GET /auth/callback?code=...&state=...

Reponse attendue (extrait):

{
  "message": "Authentication successful",
  "access_token": "eyJ...",
  "token_type": "Bearer",
  "user": {
    "uid": "mock-doctor-001",
    "provider": "esignet"
  }
}

### Profil courant

Requete:
- GET /auth/me
- Header: Authorization: Bearer <access_token>

Reponse attendue (extrait):

{
  "uid": "mock-doctor-001",
  "role": "DOCTOR",
  "provider": "esignet"
}

### Demarrer verification patient

Requete:
- POST /patients/{patient_id}/verify/start

Reponse attendue (extrait):

{
  "authorization_url": "http://localhost:9000/authorize?...",
  "state": "..."
}

### Callback verification patient

Requete:
- GET /auth/callback?code=...&state=patient_verify:{patient_id}:...

Reponse attendue (extrait):

{
  "message": "Patient identity verified successfully",
  "patient": {
    "identityStatus": "VERIFIED",
    "kycStatus": "VERIFIED_BY_PROVIDER",
    "esignetSubjectId": "mock-patient-verified-001"
  }
}

## 9) Limitations connues (honnetes)

- Sans credentials eSignet officiels, l'auth reste en mode mock pour integration.
- Un backend public seul n'est pas suffisant pour garantir un parcours auth complet si le client OIDC deploye n'est pas valide.
- Si le mock IdP n'est pas deploye publiquement, il ne sert pas aux apps distantes sans setup local ou tunnel.
- Les parcours biometrie (face/fingerprint) ne font pas partie de cette version.

## 10) Recommandation mode equipe (court terme)

Mode recommande maintenant: integration Flutter en local/mock.

Pourquoi:
- Plus rapide et stable immediatement.
- Flux auth complet deja valide localement de bout en bout.
- Firestore reste reel, donc les donnees et comportements metier sont representatifs.
- Evite de bloquer l'equipe sur la disponibilite des credentials eSignet officiels.

Option suivante quand vous voulez un test distant partage:
- deployer aussi le mock IdP sur une URL publique, puis configurer le backend public avec ce issuer + un client OIDC valide.