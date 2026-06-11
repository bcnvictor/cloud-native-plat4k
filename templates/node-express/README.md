# node-express — CNP scaffolding template

API REST minimale **Node.js / Express**, prête à être déployée par la CNP.

## Contenu

```
.
├── src/
│   ├── app.js          # routes Express (/ et /healthz)
│   └── index.js        # point d'entrée — écoute sur $PORT (défaut 8000)
├── test/app.test.js    # test node:test du endpoint /healthz
├── Dockerfile          # image node:20-alpine, écoute sur 8000
├── package.json
└── chart/templates/    # manifests Helm (deployment, service, ingress)
```

> `chart/values.yaml` et `chart/Chart.yaml` ne sont **pas** versionnés : la plateforme CNP les génère au scaffolding à partir des paramètres fournis (nom, port, image, replicas, env…).

## Prérequis

- Node.js 20+
- Docker (pour builder l'image localement)

## Développement local

```bash
npm install
npm start          # http://localhost:8000
npm test           # node:test
```

## Variables d'environnement

| Variable | Défaut | Description |
|----------|--------|-------------|
| `PORT`   | `8000` | Port d'écoute HTTP. Injecté par le chart depuis `app.port`. |

## CI (injectée par la CNP)

La plateforme injecte un `.gitlab-ci.yml` qui inclut `cnp-ci-modules/base/pipeline.yml`
et `cnp-ci-modules/frameworks/nodejs.yml`. Le job `nodejs-test` se déclenche sur la
présence de `package.json` et exécute `npm install` puis `npm run test --if-present`.

> Ne pas ajouter de `.gitlab-ci.yml` dans ce template : la CNP le génère et refuse
> l'injection si le fichier existe déjà.
