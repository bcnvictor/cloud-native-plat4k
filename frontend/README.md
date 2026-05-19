# Frontend — CNP Cloud Native Plat4k

SPA React/TypeScript pour la plateforme développeur interne CNP.

---

## Stack

| Couche | Outil |
|---|---|
| Framework | React 18 + TypeScript |
| Build | Vite 5 |
| Routing | React Router v6 |
| State serveur | TanStack Query v5 |
| State client | Zustand |
| HTTP | Axios |
| Auth JWT | jwt-decode |
| Styles | CSS custom (`index.css`) + Tailwind (config uniquement) |
| Icônes | Tabler Icons (CDN, classes `ti-*`) |

---

## Structure

```
src/
├── api/          # Couches d'accès HTTP, une par domaine
│   ├── client.ts       # Instance Axios + intercepteurs auth/refresh
│   ├── apps.ts         # Applications & déploiements
│   ├── auth.ts         # Login, logout, API keys
│   ├── credentials.ts  # Credentials cloud
│   ├── gitlab.ts       # OAuth GitLab
│   └── resources.ts    # Ressources cloud (VM, storage…)
├── components/   # Composants réutilisables
│   ├── Layout.tsx        # Shell principal : sidebar + outlet
│   ├── SettingsLayout.tsx # Shell deux-colonnes pour les pages Paramètres
│   ├── ConfirmModal.tsx   # Modal de confirmation générique
│   ├── HexLogo.tsx        # Logo SVG hexagonal
│   └── StatusBadge.tsx    # Badge coloré selon statut
├── pages/        # Pages, une par route
│   ├── Resources.tsx       # Liste des applications (page d'accueil)
│   ├── ResourceDetail.tsx  # Détail + déploiements d'une application
│   ├── Dashboard.tsx       # Monitoring
│   ├── MyProjects.tsx      # Projets GitLab de l'utilisateur
│   ├── Docs.tsx            # Documentation intégrée
│   ├── Credentials.tsx     # Gestion des credentials cloud
│   ├── ApiKeys.tsx         # Gestion des tokens d'accès
│   ├── Login.tsx           # Formulaire login + bouton GitLab SSO
│   ├── OAuthCallback.tsx   # Réception du token après OAuth GitLab
│   └── admin/
│       ├── Users.tsx       # Liste des utilisateurs (admin)
│       └── Audit.tsx       # Logs d'audit (admin)
├── router/
│   ├── index.tsx         # Définition des routes
│   └── ProtectedRoute.tsx # Guard : auth + rôle requis
├── store/
│   └── auth.ts           # Store Zustand : token + user courant
├── types/
│   └── index.ts          # Types partagés (Application, Deployment, User…)
└── utils/
    ├── appStatus.ts      # Mapping ApplicationStatus → ResourceStatus
    └── timeAgo.ts        # Formattage relatif de date (fr)
```

---

## Architecture

### Routing et accès par rôle

Le routeur est divisé en deux groupes :

- `/` — routes accessibles à tout utilisateur authentifié, rendues dans `Layout`
- `/admin` — routes protégées par `ProtectedRoute requiredRole="admin"`, rendues également dans `Layout`

`Layout` affiche conditionnellement les entrées admin (`Utilisateurs`, `Audit`) dans la sidebar selon `user.role`. `ProtectedRoute` redirige vers `/dashboard` si le rôle est insuffisant.

La page d'accueil (`/`) pointe vers `Resources` (liste des applications).

### Auth & sessions

1. **Login email/mot de passe** (`/auth/login`, OAuth2 password flow)  
   Le backend retourne un `access_token` JWT. Le frontend le décode pour en extraire `sub` (user id), `role` et `email`, puis persiste le tout dans Zustand + `localStorage`.

2. **SSO GitLab** (`/auth/gitlab/authorize` → `/oauth/callback`)  
   Le backend redirige vers `/oauth/callback#access_token=...&email=...`. `OAuthCallback` décode le fragment, lit le rôle depuis le payload JWT, et stocke la session.

3. **Refresh automatique**  
   `api/client.ts` intercepte les réponses 401. Si la requête n'est pas `/auth/login`, il tente un refresh via le cookie `refresh_token` (httpOnly). Un seul refresh est effectué en parallèle grâce à une `Promise` partagée (`refreshPromise`) — les requêtes concurrentes attendent le même résultat au lieu de déclencher chacune un refresh.

4. **Déconnexion**  
   `Layout` appelle `POST /auth/logout` (supprime le cookie) puis `clearAuth()` (vide Zustand + localStorage).

> Le rôle est encodé directement dans le payload JWT (champ `role`). Voir [ADR-0009](../docs/adr/0009-role-jwt-payload.md).

### Données serveur (TanStack Query)

Toutes les requêtes de données sont gérées par TanStack Query. Chaque page déclare ses `useQuery` / `useMutation` localement. Les `queryKey` suivent la convention `['resource-type', ...params]`.

Le cache n'est pas partagé globalement entre pages — les invalidations sont ciblées par `queryKey` après mutation.

### State client (Zustand)

Seul le store `auth` est global. Il contient `token` et `user` (avec hydratation depuis `localStorage` au démarrage). Tous les autres états sont locaux aux composants.

---

## Développement local

```bash
# depuis la racine du projet
npm install          # installe les dépendances frontend (workspace)

# ou directement
cd frontend
npm install
npm run dev          # démarre Vite sur http://localhost:5173
```

L'API cible `VITE_API_URL` (défaut : `/api/v1`). En dev, Vite proxyfie vers le backend via `vite.config.ts`.

```bash
# build de production
npm run build        # tsc + vite build → dist/
```

---

## Variables d'environnement

| Variable | Défaut | Description |
|---|---|---|
| `VITE_API_URL` | `/api/v1` | URL de base de l'API backend |

En production, le frontend est servi par Nginx (`nginx.conf`) avec proxy `/api/v1` → backend.

---

## Design system

Toutes les classes CSS sont définies dans `src/index.css`. Le projet n'utilise pas de composants Tailwind ni de librairie UI — uniquement des variables CSS et des classes utilitaires internes (`cnp-layout`, `sb-*`, `card`, `badge`, `btn`, etc.).

Tailwind est présent uniquement pour sa configuration (couleurs, breakpoints) mais les classes utilitaires `tw-` ne sont pas utilisées dans les composants.
