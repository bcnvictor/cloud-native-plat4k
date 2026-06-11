# react-vite — CNP scaffolding template

SPA frontend **React + Vite**, buildée en statique et servie par nginx, prête à être
déployée par la CNP.

## Contenu

```
.
├── index.html
├── src/
│   ├── main.jsx     # bootstrap React
│   └── App.jsx
├── vite.config.js
├── nginx.conf       # sert le build statique sur le port 8000 (+ /healthz)
├── Dockerfile       # build multi-stage Vite → image nginx
├── package.json
└── chart/templates/ # manifests Helm (deployment, service, ingress)
```

> `chart/values.yaml` et `chart/Chart.yaml` ne sont **pas** versionnés : la plateforme CNP les génère au scaffolding.

## Prérequis

- Node.js 20+
- Docker (pour builder l'image localement)

## Développement local

```bash
npm install
npm run dev        # serveur de dev Vite (http://localhost:5173)
npm run build      # build de production dans dist/
npm test           # vitest
```

## Port d'écoute

L'image nginx sert le build statique sur le **port 8000** (fixé dans `nginx.conf`).
Laisse `app.port` à `8000` lors du scaffolding ; changer le port nécessite aussi
d'éditer `nginx.conf`.

## CI (injectée par la CNP)

La plateforme injecte un `.gitlab-ci.yml` qui inclut `cnp-ci-modules/base/pipeline.yml`
et `cnp-ci-modules/frameworks/nodejs.yml`. Le job `nodejs-test` se déclenche sur la
présence de `package.json` et exécute `npm install` puis `npm run test --if-present`.

> Ne pas ajouter de `.gitlab-ci.yml` dans ce template : la CNP le génère et refuse
> l'injection si le fichier existe déjà.
