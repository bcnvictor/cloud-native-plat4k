# API REST

L'API CNP expose les ressources de la plateforme via HTTP/JSON. Authentification via Bearer token ou header `X-API-Key`.

## Base URL

```
http://localhost:8000/api/v1
```

## Endpoints principaux

| Endpoint        | Méthode | Description                          |
|-----------------|---------|--------------------------------------|
| GET /apps       | GET     | Lister les applications              |
| POST /apps      | POST    | Enregistrer une application          |
| GET /apps/:id   | GET     | Détail d'une application             |
| DELETE /apps/:id| DELETE  | Supprimer une application            |
| GET /clusters   | GET     | Lister les clusters Kubernetes       |
| POST /deployments | POST  | Déclencher un déploiement K8s        |
| GET /audit      | GET     | Consulter les logs d'audit (admin)   |
