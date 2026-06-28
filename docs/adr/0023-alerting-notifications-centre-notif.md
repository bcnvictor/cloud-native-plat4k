# ADR-0023 : Alerting in-app — événements, notifications et centre de notifications

## Statut

Accepted : 2026-06-29

## Contexte

La plateforme ne disposait d'aucun mécanisme d'information des utilisateurs sur les
événements métier significatifs (création/suppression d'app, dégradation de santé,
mouvements dans les groupes, transition cluster OFFLINE…). L'audit log existant
(`AuditLog`) ne couvre que les actions initiées par un utilisateur et n'est accessible
qu'aux admins. Il manquait un canal temps-réel visible par les membres de chaque groupe.

L'epic **4K-72** (tickets 4K-73 data, 4K-74 emit/fan-out/API, 4K-75 UI) a pour objectif
de combler ce besoin via un backbone d'alerting in-app persisté en base.

## Décision

### 1. Deux flows distincts et coexistants : AuditLog et Event→Notification

`AuditLog` conserve sa vocation de traçabilité admin (qui a fait quoi, quand). Il est
enrichi d'un champ `extra JSON nullable` pour porter des métadonnées structurées
(paramètres d'un rollback, nom avant suppression, etc.).

Un second flow, indépendant, gère l'alerting utilisateur :
- `Event` — fait métier immuable (type, sévérité, source, `app_id`, `payload`, `dedup_key`)
- `Notification` — entrée d'inbox par destinataire (`recipient_user_id`, état `new/read/acknowledged`)
- `NotificationPreference` — opt-out par catégorie (`app`, `cluster`, `group`) par utilisateur

Cette séparation évite de polluer l'audit log avec des états par-utilisateur et permet
de faire évoluer les deux flux indépendamment.

### 2. `emit_event()` synchrone et inline dans la session DB

L'émission d'un événement est une fonction async appelée directement dans la session
SQLAlchemy existante de la route (ou du worker), sans queue externe ni Celery. Elle :

1. insère l'`Event` et flush (pour obtenir `event.id`)
2. résout les destinataires via `resolve_recipients()` (admins + acteur + membres du
   groupe/app concerné)
3. filtre les destinataires ayant désactivé la catégorie de l'événement
4. insère les `Notification` correspondantes et flush

Le commit est laissé à l'appelant, qui commite l'ensemble de la transaction (action
métier + événements) en une seule passe. Aucune étape de migration DB hors Alembic.

Ce choix priorise la simplicité (pas de queue, pas de dépendance supplémentaire) au
détriment de la résilience : une panne dans `resolve_recipients()` peut faire échouer
la transaction métier. Acceptable au volume actuel ; une queue async serait la solution
si l'émission devenait un point de contention.

### 3. Sémantique d'inbox : `acknowledged` = supprimé de l'inbox

Trois états progressifs : `new` → `read` → `acknowledged`.

La liste des notifications (endpoint `GET /notifications/`) exclut par défaut les entrées
`acknowledged`. L'action "Clear all" (`POST /notifications/clear`) marque toutes les
entrées non-acknowledged comme `acknowledged` en une requête. Cela donne une sémantique
d'inbox claire : les notifications cleared disparaissent de la cloche sans être
physiquement supprimées (traçabilité conservée).

### 4. 13 types d'événements répartis en 3 catégories

```
app     : app.created, app.updated, app.deleted, app.deployed, app.rollback,
           app.health.degraded, app.health.recovered, app.expose.changed
cluster : cluster.offline, cluster.online
group   : group.renamed, group.member.added, group.member.removed
```

La catégorie détermine : les destinataires résolus (`resolve_recipients`), le filtre de
préférence applicable, et le label affiché dans l'UI.

### 5. Endpoint `GET /groups/{gitlab_group_id}/activity`

Agrège les événements pertinents pour un groupe (apps du groupe + payload `group_id`
correspondant) via une requête SQLAlchemy sur `Event.payload['group_id'].as_string()`
(`->>` PostgreSQL, extraction text). Cet endpoint alimente le panneau "Recent activity"
de la page groupe, remplaçant le stub mock précédent.

### 6. Frontend : cloche de notifications avec polling

`NotificationBell` est un composant autonome intégré dans la `Sidebar` :
- polling du badge (`/notifications/count`) toutes les 30 secondes
- popover chargé à la demande (ouverture) via `enabled: open`
- états visuels distincts : `new` = fond `bg-background` + texte bold ; `read`/`acknowledged` = fond `bg-muted` + `text-muted-foreground`
- bouton "Clear all" avec guard `isPending` et invalidation `onSettled`

Les préférences (opt-out par catégorie) sont exposées sur la page `Profile`.

## Conséquences

Positif :
- Les membres d'un groupe sont notifiés des événements concernant leurs apps sans
  requête manuelle.
- L'audit log admin et l'inbox utilisateur sont découplés et peuvent évoluer séparément.
- Pas de dépendance externe : SQLAlchemy + Postgres suffisent.

Négatif / Dette :
- `emit_event()` est dans la transaction métier : une erreur de fan-out (ex: Vault
  indisponible lors de `resolve_recipients`) peut annuler l'action déclenchante.
- Pas de deduplication temps-réel : le `dedup_key` est calculé mais pas utilisé pour
  bloquer les doublons en base (pas de contrainte UNIQUE sur `events.dedup_key`).
- Le polling 30 s côté frontend est un compromis simplicité/fraîcheur. WebSocket ou
  SSE serait plus réactif mais alourdirait l'architecture.

Neutre :
- Les routes `GET /groups/{id}/activity` partagent le modèle `EventResponse` avec le
  système de notifications — un seul type Pydantic à maintenir.
- Les événements historiques (avant l'introduction de ce système) ne sont pas rétro-générés.
