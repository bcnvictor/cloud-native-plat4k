# CNP Frontend — frontend-new

Nouveau frontend de la Cloud Native Platform (ticket 4k-88). SPA React 18 servie par Nginx, remplaçant `frontend/`.

## Stack

| Rôle | Lib |
|---|---|
| UI | React 18 + TypeScript |
| Build | Vite 5 |
| Style | Tailwind CSS 3 |
| Routing | React Router DOM v6 |
| Cache & fetching | TanStack React Query v5 |
| État global | Zustand v4 |
| HTTP | Axios 1.x |
| Icônes | @tabler/icons-react |
| Charts | Recharts |
| Tests unitaires | Vitest + Testing Library |
| Tests e2e | Playwright |

## Lancement en développement

```bash
cd frontend-new
npm install
cp .env.example .env.local  # ajuster VITE_API_URL si besoin
npm run dev                  # http://localhost:5173
```

Variable d'environnement disponible :

| Variable | Défaut | Description |
|---|---|---|
| `VITE_API_URL` | `/api/v1` | URL de base de l'API backend |

## Structure des sources

```
src/
├── api/          # Modules d'appel API (un fichier par domaine)
│   ├── client.ts         # Instance axios + intercepteurs auth
│   ├── auth.ts
│   ├── apps.ts
│   ├── groups.ts
│   ├── clusters.ts
│   ├── finops.ts
│   ├── monitoring.ts
│   ├── audit.ts
│   ├── users.ts
│   └── gitlab.ts
├── components/
│   ├── ui/       # Primitives réutilisables (Button, Card, Badge, Input…)
│   └── nav/      # TopNav, NavItems, ScopeSwitcher
├── hooks/        # Hooks métier (useCurrentGroup, useGroupApps, useAppMetrics…)
├── layouts/
│   ├── RootLayout.tsx      # Coquille commune (TopNav + Toaster + Outlet)
│   └── AppDetailLayout.tsx # Layout onglets d'une application
├── pages/
│   ├── Login.tsx / OAuthCallback.tsx / Profile.tsx
│   ├── group/              # Espace groupe
│   │   ├── GroupHome.tsx
│   │   ├── GroupApps.tsx
│   │   ├── GroupSettings.tsx
│   │   └── app/
│   │       ├── NewApp/     # Wizard création (4 étapes)
│   │       └── tabs/       # OverviewTab, DeploymentsTab, LogsTab, SettingsTab
│   └── admin/              # Espace admin (réservé is_admin)
│       ├── Clusters.tsx
│       ├── FinOps.tsx
│       ├── AdminApps.tsx
│       ├── AdminUsers.tsx
│       ├── AdminAudit.tsx
│       └── AdminSettings.tsx
├── router/
│   ├── index.tsx   # Déclaration des routes
│   └── guards.tsx  # ProtectedRoute, AdminRoute, RootRedirect
├── store/
│   ├── auth.ts     # useAuthStore (token + user, persisté localStorage)
│   └── scope.ts    # useScopeStore (group | admin + slug actif)
├── types/
│   └── index.ts    # Tous les types TypeScript du domaine
└── utils/          # cn(), slugify(), timeAgo(), appHealth…
```

## Architecture

### Client HTTP (`src/api/client.ts`)

Instance Axios unique exportée `api`. Deux intercepteurs :

- **Request** : injecte le Bearer token depuis `useAuthStore`.
- **Response** : sur 401, tente un refresh via `POST /auth/refresh` (avec déduplication — un seul appel concurrent). En cas d'échec du refresh, efface l'auth et redirige vers `/login`.

### État global (Zustand)

Deux stores légers, sans middleware de persistance (gestion manuelle via `localStorage`) :

- **`useAuthStore`** — `token`, `user`, `setAuth()`, `clearAuth()`. Initialisé depuis `localStorage` au chargement.
- **`useScopeStore`** — `activeScope` (`'group' | 'admin'`) + `activeGroupSlug`. Mis à jour par chaque page au montage via `setScope()`.

### Routing & guards (`src/router/`)

```
/login                    → Login (public)
/oauth/callback           → OAuthCallback (public)
/                         → RootRedirect (protected)

ProtectedRoute (token requis)
└── RootLayout
    ├── /groups/:slug                → GroupHome
    ├── /groups/:slug/apps           → GroupApps
    ├── /groups/:slug/apps/new       → NewApp (wizard)
    ├── /groups/:slug/apps/:appSlug  → AppDetailLayout
    │   ├── (index)                  → OverviewTab
    │   ├── deployments              → DeploymentsTab
    │   ├── logs                     → LogsTab
    │   └── settings                 → SettingsTab
    ├── /groups/:slug/settings       → GroupSettings
    └── /profile                     → Profile

AdminRoute (token + is_admin requis)
└── RootLayout
    ├── /admin/clusters   → Clusters
    ├── /admin/finops     → FinOps
    ├── /admin/apps       → AdminApps
    ├── /admin/users      → AdminUsers
    ├── /admin/audit      → AdminAudit
    └── /admin/settings   → AdminSettings
```

**`RootRedirect`** : redirige automatiquement vers le premier groupe de l'utilisateur, ou `/admin/clusters` pour un admin sans groupe.

### Wizard de création d'application (`NewApp`)

4 étapes gérées en local state :

1. **Identité** — nom, origin (`scaffold` depuis template ou `onboard` depuis repo existant), framework.
2. **Services** — base de données (PostgreSQL, taille PVC), auth, cache (Redis).
3. **CI & Déploiement** — trigger (`on_commit` / `on_tag`), variables d'environnement, replicas, cluster cible.
4. **Récap** — revue et soumission.

La navigation entre étapes est bloquée (`useBlocker`) pendant la mutation de création.

### Data fetching

TanStack Query v5 avec `staleTime: 30 000 ms` par défaut (configurable par query). Les mutations invalident les query keys concernées (`['apps']`, `['my-groups']`…).

## Tests

```bash
npm run test           # Vitest (unitaire)
npm run test:watch     # Vitest en mode watch
npm run test:e2e       # Playwright (nécessite un backend actif)
```

Les tests e2e couvrent : affichage du formulaire de login, redirections selon le rôle (admin/dev), accès non authentifié aux routes protégées.

## Build & Déploiement

### Build statique

```bash
npm run build   # → dist/
```

L'image Docker est un build multi-stage :

```
node:20-alpine  → npm ci + vite build → dist/
nginx:alpine    → sert dist/ sur :80
```

`VITE_API_URL` est passé comme `ARG` Docker au build time (défaut `/api/v1`).

### Nginx

- SPA fallback : toutes les routes inconnues renvoient `index.html`.
- Assets Vite (noms hashés) : cache `1y`.
- `index.html`, `logo.png`, `favicon.svg` : `no-cache`.
- Proxy `/api/` → `http://backend:8000/api/` (si pas géré par le reverse proxy amont).

## Conventions

- Chemins absolus via l'alias `@/` → `src/`.
- Un fichier par domaine dans `src/api/`, exportant un objet `xxxApi`.
- Les composants UI dans `src/components/ui/` n'ont pas de dépendances métier.
- `cn()` (`src/lib/cn.ts`) combine `clsx` + `tailwind-merge`.
