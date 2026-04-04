# Note Flutter - Test distant complet (backend + mock OIDC)

Date: 2026-04-04

## URLs publiques a utiliser

- Backend API: https://afya-id-419586439350.europe-west2.run.app
- Mock OIDC/eSignet: https://afya-mock-oidc-tpetcpbucq-nw.a.run.app
- Callback backend: https://afya-id-419586439350.europe-west2.run.app/auth/callback

## Comment se connecter depuis Flutter

1. Appeler `GET /auth/login` sur le backend.
2. Recuperer `authorization_url`.
3. Ouvrir cette URL dans navigateur externe ou webview.
4. Se connecter avec un utilisateur mock (voir section ci-dessous).
5. Le provider redirige vers le callback backend public.
6. Le callback retourne `access_token` et `user` en JSON.
7. Appeler `GET /auth/me` avec `Authorization: Bearer <access_token>`.

## Utilisateurs mock de test

- admin.mock / Admin123!
- doctor.mock / Doctor123!
- healthworker.mock / Health123!
- responder.mock / Responder123!
- patient.verified / Patient123!
- patient.pending / Patient123!

## Endpoints utiles apres login

- `GET /auth/me`
- `POST /auth/complete-profile`
- `POST /patients/register`
- `POST /patients/{patient_id}/verify/start`
- `GET /patients/{patient_id}`
- `GET /patients/{patient_id}/summary`
- `GET /patients/{patient_id}/emergency`
- `POST /kyc/submit`

## Notes importantes

- Firebase/Firestore reste reel sur le projet `afya-id`.
- Le provider d'identite est un mock distant (pas eSignet officiel).
- Le flow est 100% distant: aucun `localhost` n'est requis pour les tests Flutter.