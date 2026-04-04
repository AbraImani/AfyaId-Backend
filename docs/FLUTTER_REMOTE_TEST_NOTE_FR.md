# Note Flutter - Integration distante complete (backend public avec un mock OIDC déja public sur cloud run)

Date: 2026-04-04

## 1) Ce qui est en place maintenant

- Backend API public: https://afya-id-419586439350.europe-west2.run.app
- Mock OIDC/eSignet public: https://afya-mock-oidc-tpetcpbucq-nw.a.run.app
- Callback backend public: https://afya-id-419586439350.europe-west2.run.app/auth/callback
- Firestore: production (de projet afya-id)

Conclusion pratique:
- La team Flutter vous pouvait tester tout le flow en distant, sans localhost.

## 2) Pourquoi l'interface de login peut apparait du HTML

L'ecran que vous voyez (formulaire HTML basique) est normal.

- Ce provider est un mock de test d'integration, pas l'UI officielle eSignet.
- L'objectif est de valider le protocole OIDC (authorize, token, userinfo, jwks), pas le design UI final.
- En production, cette UI sera remplacee par le vrai portail eSignet, une fois en possession de credentials.

## 3) Flux d'auth recommande pour Flutter (important)

Le backend est configure pour ce contrat:

1. Flutter appelle GET /auth/login
2. Backend renvoie:
	 - authorization_url
	 - state
3. Flutter ouvre authorization_url dans une WebView (ou navigateur in-app)
4. Utilisateur se connecte sur le mock
5. Le mock tente de rediriger vers /auth/callback?code=...&state=...
6. Flutter intercepte cette URL de callback
7. Flutter appelle lui-meme cette URL callback via son client HTTP
8. Backend repond avec JSON contenant access_token, id_token, user
9. Flutter stocke access_token et l'utilise en Bearer sur les endpoints proteges

Pourquoi cette methode est la meilleure:
- Elle evite de depender de la lecture du body JSON dans la WebView.
- Elle garde la logique API claire et testable.

## 4) Gestion du token sans ambiguite

Reponse attendue sur callback:

{
	"access_token": "eyJ...",
	"id_token": "eyJ...",
	"token_type": "Bearer",
	"user": { ... },
	"kyc_status": "...",
	"profile_complete": true,
	"message": "..."
}

Utilisation:
- Header Authorization: Bearer <access_token>
- Endpoint de verification session: GET /auth/me

Stockage recommande cote Flutter:
- Conserver access_token en stockage securise (pas en clair).
- Sur 401, relancer le flow login.

## 5) Strategie d'implementation Flutter pour le WebView

Recommande:
- Ouvrir authorization_url dans WebView.
- Dans shouldOverrideUrlLoading (ou equivalent), detecter les URLs qui commencent par:
	- https://afya-id-419586439350.europe-west2.run.app/auth/callback
- Annuler la navigation WebView vers cette URL.
- Fermer la WebView.
- Faire un GET HTTP depuis Flutter sur cette URL interceptee.
- Extraire access_token depuis le JSON backend.

Attention importante:
- Il faut annuler la navigation avant que la WebView n'appelle vraiment /auth/callback,
	sinon le state peut etre consomme et un second appel peut echouer.

## 6) Utilisateurs mock de test

- admin.mock / Admin123!
- doctor.mock / Doctor123!
- healthworker.mock / Health123!
- responder.mock / Responder123!
- patient.verified / Patient123!
- patient.pending / Patient123!

## 7) Endpoints utiles apres login

- GET /auth/me
- POST /auth/complete-profile
- POST /patients/register
- POST /patients/{patient_id}/verify/start
- GET /patients/{patient_id}
- GET /patients/{patient_id}/summary
- GET /patients/{patient_id}/emergency
- POST /kyc/submit

## 8) Verification patient depuis Flutter

Flow:

1. Auth staff (doctor ou healthworker)
2. Creer patient via POST /patients/register
3. Lancer verification via POST /patients/{patient_id}/verify/start
4. Ouvrir authorization_url recu
5. Intercepter callback comme pour le login
6. Appeler callback en HTTP
7. Verifier dans la reponse patient:
	 - identityStatus
	 - kycStatus
	 - esignetSubjectId

## 9) Checklist integration Flutter

- GET /auth/login renvoie une URL publique
- Ecran mock de login s'affiche
- Callback est intercepte
- Callback HTTP renvoie access_token
- GET /auth/me fonctionne avec Bearer
- Au moins une route patient protegee fonctionne

## 10) Notes de confiance

- Firebase/Firestore reste reel sur le projet afya-id.
- Le provider d'identite est un mock distant (pas eSignet officiel).
- Le flow de test est 100% distant: aucun localhost n'est requis.

## 11) Pseudo-code Flutter (interception callback)

Un simple exemple alogorithmique à adapter au package WebView cote Flutter: 

1. loginResp = GET /auth/login
2. openWebView(loginResp.authorization_url)
3. onNavigation(url):
	 - if url startsWith("https://afya-id-419586439350.europe-west2.run.app/auth/callback"):
		 - cancel WebView navigation
		 - close WebView
		 - callbackResp = GET url
		 - token = callbackResp.access_token
		 - secureStore.write("access_token", token)
		 - me = GET /auth/me with Authorization: Bearer token
		 - continue app session with me.user

Je ne sais pas comment ça va se passer dee votre côté mais si vous utilisez un navigateur externe au lieu de WebView, il va vous falloir :
- configurez un deep link de retour app,
- ou gardez une page intermediaire frontend qui recupere le JSON callback et le renvoie vers l'app.