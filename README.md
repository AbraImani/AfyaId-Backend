# AfyaId-Backend

Backend FastAPI pour AfyaID (prototype v1.0.0) : gestion des patients, RBAC, KYC et integration eSignet (encore en mode mock pour la partie login reel).

## Liens utiles

- API de production: https://afya-id-419586439350.europe-west2.run.app
- Swagger UI: https://afya-id-419586439350.europe-west2.run.app/docs
- OpenAPI JSON: https://afya-id-419586439350.europe-west2.run.app/openapi.json
- Documentation detaillee (FR): docs/API documentation.md

## Statut du prototype

- Disponible maintenant: CRUD patient, vues summary/emergency, routes admin, KYC, Firebase cloud reel.
- En attente des credentials eSignet reels: /auth/login, /auth/callback, verification patient via eSignet.
- Non inclus dans cette version: reconnaissance faciale et empreinte digitale.