# AfyaId-Backend

Backend FastAPI pour AfyaID (prototype v1.0.0) : gestion des patients, RBAC, KYC et integration eSignet (encore en mode mock pour la partie login reel).

## Liens utiles

- API de production: https://afya-id-419586439350.europe-west2.run.app
- Swagger UI: https://afya-id-419586439350.europe-west2.run.app/docs
- OpenAPI JSON: https://afya-id-419586439350.europe-west2.run.app/openapi.json
- Documentation detaillee (FR): docs/API documentation.md
- Setup local mock OIDC/eSignet (FR): docs/MOCK_ESIGNET_LOCAL_SETUP_FR.md
- Guide Flutter local/mock (FR): docs/FLUTTER_TEAM_LOCAL_MOCK_GUIDE_FR.md

## Statut du prototype

- Disponible maintenant: CRUD patient, vues summary/emergency, routes admin, KYC, Firebase cloud reel.
- Mode local mock OIDC disponible via Docker: /auth/login, /auth/callback, /auth/me et verification patient via eSignet mock.
- Non inclus dans cette version: reconnaissance faciale et empreinte digitale.