# ADR-0009 : Rôle utilisateur encodé dans le payload JWT

## Statut

Accepted

## Contexte

Le frontend doit connaître le rôle de l'utilisateur connecté (`admin` ou `viewer`) pour :
- afficher ou masquer les entrées admin dans la sidebar
- bloquer la navigation vers `/admin/*` côté client via `ProtectedRoute`

Deux approches ont été envisagées pour transmettre cette information au frontend.

**Option A — Endpoint `/users/me`**  
Après login, le frontend effectue une requête `GET /users/me` pour récupérer le profil complet (dont le rôle). Le token JWT ne contient que `sub` (l'identifiant utilisateur).

**Option B — Champ `role` dans le payload JWT**  
Le backend inclut le rôle directement dans le payload JWT au moment de la signature. Le frontend décode le token localement (sans requête réseau) pour lire le rôle.

L'option A avait été implicitement supposée pendant un temps, alors que l'option B avait été choisie dans le design du frontend (`Login.tsx` lit `payload.role`). Cette divergence a produit un bug silencieux : tous les utilisateurs, y compris les admins, étaient traités comme `viewer` par le frontend, car `payload.role` était `undefined` et le fallback codé en dur était `'viewer'`.

## Décision

Nous avons décidé d'encoder le rôle dans le payload JWT (option B) et de corriger le backend pour qu'il inclue systématiquement `role` lors de la signature du token (`create_access_token`).

Cette approche est cohérente avec le flow OAuth GitLab déjà en place, où le backend passait déjà `role` dans les paramètres de redirection (mais pas dans le JWT lui-même, ce qui était également corrigé).

Le refresh de token relit le rôle depuis la base de données avant de signer le nouveau JWT, garantissant que le rôle est toujours à jour après un changement côté admin.

## Conséquences

Positif :
- Aucune requête réseau supplémentaire au démarrage de l'application pour déterminer le rôle.
- Cohérence entre le flow login classique et le flow OAuth GitLab.
- Le rôle est disponible immédiatement, y compris pour le rendu initial de la sidebar.

Négatif / Dette :
- Si le rôle d'un utilisateur est modifié en base, le changement n'est effectif côté frontend qu'à l'expiration du token d'accès (ou à l'appel du endpoint `/auth/refresh`). Pendant cette fenêtre, la sidebar peut afficher des entrées admin à un utilisateur dont le rôle vient d'être révoqué — ou inversement ne pas les afficher à un nouveau admin.
- Le backend doit veiller à inclure `role` dans **tout** chemin qui crée un JWT d'accès (login, refresh, OAuth callback). Un oubli reproduit silencieusement le bug.

Neutre :
- La vérification du rôle côté client reste purement cosmétique (affichage/navigation). L'autorisation réelle est toujours appliquée par le backend sur chaque endpoint (`/users/`, `/audit/`).
