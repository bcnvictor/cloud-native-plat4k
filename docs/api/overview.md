# API REST

Le backend CNP expose une API REST documentée au format **OpenAPI**. La spécification
est versionnée dans ce dépôt (`docs/api/openapi.json`) afin que cette documentation reste
consultable sans dépendre d'une API live.

- **Base URL (dev)** : `http://localhost:8000/api/v1`
- **Authentification** : clé d'API via l'en-tête `X-API-Key`, ou JWT `Bearer`.
- **Swagger UI live** : `http://localhost:8000/api/v1/docs`

!!! note "Spécification versionnée"
    L'`openapi.json` ci-dessous est un instantané généré depuis le backend
    (`curl http://localhost:8000/api/v1/openapi.json`). Régénérez-le lorsque l'API change.

## Explorateur Swagger UI

<swagger-ui src="openapi.json"/>
