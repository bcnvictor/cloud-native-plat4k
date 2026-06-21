# ADR-0017 : Refonte UI/UX du frontend (frontend-new/)

## Statut

Accepted

## Contexte

L'ancien `frontend/` était une SPA React fonctionnelle mais présentait plusieurs limites structurelles :

- Pas de séparation claire entre l'espace groupe (vue développeur) et l'espace admin (vue opérateur plateforme) — la navigation était ambiguë pour les utilisateurs ayant les deux rôles.
- La création d'une application était un formulaire monolithique, difficile à guider et à valider étape par étape.
- Aucun mécanisme de refresh automatique du JWT : un token expiré forçait une reconnexion manuelle.
- Les appels API n'avaient pas de stratégie de cache : chaque montage de composant redéclenchait un fetch.
- Le modèle de rôles a évolué (ajout de `tier_cnp` sur les membres, `CnpTier`, `AppOrigin`, `DeployTrigger`) sans que l'UI suive.

Le ticket 4k-88 a déclenché un rework complet de l'interface.

## Décision

Nous avons décidé de créer un nouveau répertoire `frontend-new/` en parallèle de `frontend/`, partageant la même stack de base (React + Vite + TypeScript + Tailwind) mais avec une architecture révisée sur les points suivants.

### 1. Modèle de scope group / admin

Deux espaces distincts dans le routing et la navigation, gouvernés par deux guards :

- **`ProtectedRoute`** — token JWT présent.
- **`AdminRoute`** — token présent **et** `user.is_admin === true` ; sinon redirection vers le premier groupe.

Un store Zustand `useScopeStore` (non persisté) maintient le scope actif (`'group' | 'admin'`) et le slug du groupe courant. Chaque page appelle `setScope()` à son montage pour que la navigation (`TopNav`, `ScopeSwitcher`) reste cohérente.

### 2. Refresh automatique du JWT avec déduplication

L'intercepteur de réponse Axios (`src/api/client.ts`) intercepte les 401 et appelle `POST /auth/refresh` (cookie HttpOnly). Un `refreshPromise` singleton garantit qu'un seul appel de refresh est en vol simultanément, même si plusieurs requêtes échouent en parallèle. En cas d'échec du refresh, l'auth est effacée et l'utilisateur est renvoyé vers `/login`.

### 3. TanStack Query v5 pour le cache

Tous les appels GET passent par React Query (`useQuery`) avec un `staleTime` global de 30 s. Les mutations invalident explicitement les query keys concernées. Cela supprime les re-fetch inutiles au changement d'onglet et améliore la réactivité perçue.

### 4. Wizard de création d'application en 4 étapes

Le formulaire de création est décomposé en 4 étapes séquentielles avec état local :

1. **Identité** — nom, origin (`scaffold` / `onboard`), framework ou URL de repo.
2. **Services** — base PostgreSQL (avec choix de taille PVC), auth, cache Redis.
3. **CI & Déploiement** — trigger, variables d'environnement, replicas, cluster cible.
4. **Récap** — revue complète avant soumission.

La navigation est bloquée (`useBlocker`) pendant la mutation de création pour éviter une double soumission ou une navigation accidentelle.

### 5. Layouts dédiés

- **`RootLayout`** — barre de navigation (`TopNav`) + `Outlet` + `Toaster`. Partagé par toutes les routes authentifiées.
- **`AppDetailLayout`** — onglets (`Overview`, `Deployments`, `Logs`, `Settings`) avec routes imbriquées React Router.

### 6. Coexistence avec l'ancien frontend pendant la transition

`frontend/` est conservé et continue de fonctionner. `frontend-new/` est construit et servi indépendamment (même Dockerfile multi-stage, port distinct en dev). La migration se fait en basculant le reverse proxy vers le nouveau service une fois la parité fonctionnelle atteinte.

## Conséquences

**Positif :**
- La séparation group/admin rend la navigation prévisible pour tous les profils d'utilisateurs.
- Le refresh automatique élimine les déconnexions intempestives sur les longues sessions.
- TanStack Query supprime le boilerplate de loading/error state et améliore les performances perçues.
- Le stepper guidé réduit les erreurs de configuration à la création d'une application.

**Négatif / Dette :**
- L'état du wizard (`NewApp`) est perdu si l'utilisateur recharge la page ; une persistance `sessionStorage` pourrait être ajoutée.
- Les tests e2e Playwright nécessitent un backend actif avec des comptes de test dédiés (`admin-e2e@cnp.test`, `dev-e2e@cnp.test`), ce qui les rend dépendants de l'environnement.

**Neutre :**
- Le choix de Zustand (sans middleware `persist`) implique une initialisation manuelle depuis `localStorage` dans `useAuthStore`. C'est intentionnel pour garder un contrôle explicite sur ce qui est sérialisé.
