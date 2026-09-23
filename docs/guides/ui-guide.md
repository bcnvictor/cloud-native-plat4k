# Guide de l'interface CNP (Plat4k)

Cette page décrit chaque écran de la console web, où trouver chaque fonctionnalité et qui peut l'utiliser. Elle sert de référence à l'assistant Plat4k : en cas de doute, c'est elle qui fait foi sur les menus, onglets et boutons.

## Structure générale de l'écran

- **Barre latérale gauche (sidebar)** : sélecteur de contexte en haut, menu de navigation, bouton **AI Assistant** et menu utilisateur en bas (email, **My profile**, **Sign out**). Elle se replie avec le bouton « Collapse sidebar ».
- **Sélecteur de contexte** (« Sélectionner un groupe ») : liste les groupes GitLab dont l'utilisateur est membre ; un administrateur voit aussi l'entrée **Platform** (badge admin) qui ouvre l'espace d'administration.
- **Barre du haut (TopNav)** : fil d'Ariane (ex. `Team A › Apps › mon-app`) et cloche **Notifications**.
- **Assistant Plat4k** : la mascotte en bas à droite (ou le bouton AI Assistant de la sidebar) ouvre le tiroir de chat. La mascotte peut être masquée par un administrateur ; le bouton de la sidebar reste disponible.

## Rôles et permissions

Les rôles viennent de GitLab (appartenance au groupe ou au projet) :

| Rôle CNP | Niveau GitLab | Peut faire |
|---|---|---|
| Viewer | Guest/Reporter | Consulter apps, logs, historique, métriques |
| Developer | Developer | + variables d'environnement **dev** (jamais les clés prod) |
| Maintainer | Maintainer | + renommer/supprimer une app, exposition internet, stop/resume, rollback, variables prod, réglages IA de l'app, inviter des membres |
| Owner | Owner | Tous les droits du groupe |

Le rôle **Admin plateforme** (compte CNP) donne accès à l'espace **Platform** et à toutes les applications.

## Espace groupe — Home

Chemin : sélecteur de contexte → choisir un groupe → **Home** (`/groups/<groupe>`).

- **Overview** : cartes **Average CPU**, **Total RAM** (Prometheus), **Apps by status** (healthy, deploying, unhealthy, stopped…) et **Applications** (nombre).
- **Recent activity** : derniers événements du groupe (app créée, déployée, rollback, dégradée/rétablie, arrêtée/relancée, arrêt nocturne, membre ajouté/retiré, groupe renommé).
- **Members** : membres du groupe avec leur rôle ; bouton **Invite member** qui mène aux Settings du groupe.

## Espace groupe — Apps

Chemin : groupe → **Apps** (`/groups/<groupe>/apps`).

- Liste des applications du groupe avec leur statut de santé, le cluster cible et l'origine.
- Champ **Search…** pour filtrer, bouton filtre.
- Bouton **New app** pour créer une application (voir « Créer une application »).
- Cliquer sur une application ouvre sa page de détail.

## Créer une application (New app)

Chemin : groupe → **Apps** → bouton **New app** (`/groups/<groupe>/apps/new`). Assistant en 4 étapes :

1. **Identity** : choisir l'origine — **Scaffold** (crée un nouveau projet GitLab depuis un template) ou **Onboard** (référence un repo GitLab existant) —, le **App name** (le slug est calculé automatiquement), le **Framework** (template, ex. FastAPI, Next.js, Django, Express) ou le **GitLab repo** à importer.
2. **Services** : injecter des services managés — **Database** (PostgreSQL in-cluster, nom de base et taille 1/5/20 Gi), **Authentication** (Keycloak), **Cache** (Redis).
3. **CI & Deploy** : **Target cloud** (cluster cible ; sans cluster enregistré, celui par défaut est utilisé), **Deploy trigger** (**On every commit** sur main, ou **On tag**), **Internet exposure** (sous-domaines `<slug>.cloud-native-plat4k.me` en prod et `dev.<slug>.cloud-native-plat4k.me` en dev ; disponible seulement sur les clusters avec nginx-ingress, sinon accès par port-forward), **Advanced options** (variables d'environnement, **Replica count**).
4. **Recap** : vérifier puis **Create app**. L'application passe en statut *onboarding* pendant le provisioning (repo, CI, ArgoCD).

Tout reste modifiable ensuite dans l'onglet Settings de l'application.

## Page d'une application — en-tête et onglets

Chemin : groupe → **Apps** → cliquer sur l'application (`/groups/<groupe>/apps/<app>`).

En-tête : nom, description, lien vers le dépôt source. Si l'application est en erreur, un bandeau « The application is in error » propose d'ouvrir les logs.

Onglets : **Overview**, **Logs**, **History**, **Settings**, **Assistant**.

## Onglet Overview (état, métriques, stop/resume)

- Cartes **CPU** (millicores), **RAM**, **Replicas** (prêts/désirés) et **Last sync**, avec mini-graphes ; lien vers Grafana. « Metrics unavailable » signifie que Prometheus n'est pas joignable.
- Cartes **Production environment** et **Dev environment** : état ArgoCD **Sync** (Synced/OutOfSync), **Health** (Healthy, Progressing, Degraded, Missing, Stopped), **Image** déployée, **Last sync**.
- **Stop / Resume** par environnement (maintainer+) : **Stop** puis **Confirm** met l'environnement à zéro réplica via un commit GitOps (*scale-to-zero*) ; **Resume** le relance. Les environnements dev peuvent aussi être arrêtés automatiquement la nuit (voir « Arrêt nocturne »).
- **Cloud target** : cluster cible, endpoint et statut (online/offline).
- **Quick access** : URLs prod/dev si l'app est exposée, sinon la commande `kubectl port-forward svc/<slug> 8080:80` ; lien **GitLab repository**.

## Onglet Logs

- Sélecteurs d'environnement (**dev** / **prod**) et de niveau (**ALL**, **INFO**, **WARN**, **ERROR**), champ **Search logs…**.
- Flux en direct (Loki), lignes ERROR surlignées.
- **Open in Loki** (Grafana Explore) et **Export** (fichier texte).
- « Loki unavailable » : la stack de logs du cluster n'est pas joignable.

## Onglet History (déploiements et rollback)

- **Deployment history** séparé en **Production** et **Development** : révision (SHA), date, initiateur (utilisateur ou *auto-sync*). La plus récente est marquée *current*.
- **Rollback** (maintainer+) : sur une ancienne révision, **Rollback** puis **Confirm** redéploie cette révision via ArgoCD.

## Onglet Settings (application)

- **Identity** : **Display name**, **Slug** (immuable), **Description**, bouton **Save** (maintainer+).
- **Environment variables** : onglets **dev** / **prod**, bouton **Add** (clé + valeur), **Edit**, suppression. Les valeurs ne sont jamais réaffichées après enregistrement ; elles sont stockées dans Vault et synchronisées vers le cluster en quelques minutes (redémarrage des pods). Developer : dev uniquement ; prod : maintainer+.
- **Internet exposure** : interrupteur *Exposed on internet* / *Port-forward only* (maintainer+).
- **Danger zone** : **Delete this app** (maintainer+, irréversible ; pour une app scaffoldée le repo GitLab est aussi supprimé).

## Onglet Assistant (IA d'une application)

- **AI Assistant settings** (maintainer+) : **Assistant enabled** (active le chat sur cette app), **Code access** (inclut des extraits de code ; avertissement à accepter), **Security scan** (gitleaks, semgrep, trivy…), **AI scan summary**.
- Zone de chat « Ask anything about this application » : questions sur le statut, les événements, les métriques et les coûts de l'app.
- Si la plateforme a désactivé l'IA, le message « AI assistant inactive » s'affiche.

## Espace groupe — Metrics

Chemin : groupe → **Metrics** (`/groups/<groupe>/metrics`). Tableaux de bord Grafana intégrés :

- Onglet **Overview** : **Active apps**, **Pods running**, **Est. cost 30d**, **Restart count**, widget FinOps (coût 30 jours par app).
- Onglet **Deep Dive** : **CPU per app**, **RAM per app**, **Restarts per pod**, **Pod readiness**, **Logs**.
- Bouton **View in Grafana**. « Metrics unavailable » : aucune app déployée pour ce groupe ou Grafana non configuré.

## Espace groupe — Settings (membres)

Chemin : groupe → **Settings** (`/groups/<groupe>/settings`).

- **Identity** : **Group name** (le nom de référence reste celui du groupe GitLab).
- **Members** : inviter par **GitLab email or username** avec un rôle (**Viewer**, **Developer**, **Maintainer**, **Owner**) ; liste des membres avec leur rôle, suppression ; section **Pending invitations**.
- Les membres sont synchronisés depuis GitLab : un changement fait dans GitLab apparaît après la synchronisation (ou via **Sync teams** dans le profil).

## Notifications

La cloche **Notifications** (barre du haut) liste les événements : déploiement réussi, rollback, app dégradée/rétablie, exposition modifiée, arrêt/relance, arrêt nocturne (« Scaled down for the night ») et réveil (« Woke up for the day »), cluster hors ligne/en ligne, ajout/retrait d'un groupe. Bouton **Clear all**. Les catégories reçues se règlent dans **My profile → Préférences de notification** (Applications, Clusters, Groupes).

## Arrêt nocturne des environnements dev

Quand la planification est activée par la plateforme, les environnements **dev** passent à zéro réplica le soir (20 h, heure de Paris) et redémarrent le matin (8 h), en semaine uniquement. Les événements correspondants apparaissent dans l'activité et les notifications. Un environnement arrêté peut être relancé à la main avec **Resume** (onglet Overview).

## My profile

Chemin : menu utilisateur (bas de la sidebar) → **My profile** (`/profile`).

- **Identity** : email, rôle, admin, GitLab ID, ancienneté.
- **My GitLab groups** : groupes et rôle CNP ; bouton **Sync teams** pour resynchroniser les appartenances GitLab.
- **Préférences de notification**.
- **API keys** : créer une clé (label, ex. « CI pipeline ») pour le CLI ou l'API REST — elle n'est affichée qu'une fois ; révocation via l'icône corbeille.

## Espace Platform (administrateurs)

Accès : sélecteur de contexte → **Platform** (admin uniquement). Menu : **Clusters**, **Apps**, **FinOps**, **Users**, **Audit**, **Settings**.

- **Clusters** : clusters enregistrés, statut (**Online**, **Offline**, **Unknown**), dernière activité, liens **Prometheus**, **Loki**, **ArgoCD**.
- **Apps** : catalogue de toutes les applications (nom, groupe, cluster, origine, santé).
- **FinOps** : coût total 30 jours, tendance, **Top 5 most expensive apps**, **Cost by team** (panneaux Grafana), bouton **Open in Grafana**.
- **Users** : utilisateurs, rôle (Admin, Dev, Viewer), statut ; bouton **Sync teams & users**.
- **Audit** : journal des actions (horodatage, utilisateur, action, app, détails, IP), filtres **From** / **To**, **Export CSV**.
- **Settings** (« Platform settings ») : voir la section suivante.

## Platform settings (administrateurs)

Chemin : Platform → **Settings** (`/admin/settings`).

1. **Global settings** : **Platform name**, **Public URL**.
2. **Assistant IA** : **Activer l'assistant IA** (toute la plateforme), **Afficher le bot graphique** (mascotte), **Accès aux données de la CNP** (documentation + données plateforme pour l'assistant global), **Accès aux données d'une application / repo GitLab** + sélection des applications autorisées (aucune sélection = aucune app détaillée accessible à l'assistant), **Provider IA** (Mock, Mistral UE, Gemini US, DeepSeek Chine — info-bulle « i » sur la souveraineté), **Modèle**, **Clé API** (chiffrée, jamais réaffichée).
3. **GitLab connection** : **GitLab instance URL**, **Root group**, **Token service account**, bouton **Test connection**.
4. **Register cluster** : **Name**, **Endpoint API**, kubeconfig (stocké chiffré, seul le contexte actif est utilisé), bouton **Register cluster**.

## Utiliser l'assistant Plat4k

L'assistant global (mascotte ou bouton AI Assistant) :

- connaît la page ouverte : « État des apps ? » sur la page d'un groupe porte sur ce groupe, « Ses métriques ? » sur une application porte sur cette application ;
- consulte en direct, avec les droits de l'utilisateur, l'état des applications (statut, pipeline CI, ArgoCD dev/prod, arrêt), les métriques CPU/RAM, les coûts 30 jours, les membres d'un groupe et l'activité récente ;
- explique où trouver une fonctionnalité et comment l'utiliser, à partir de cette documentation ;
- ne fait aucune action : il ne déploie pas, n'arrête pas, ne modifie rien — il indique le bouton à utiliser.

Les détails d'une application (événements, statut ArgoCD, métriques, coûts) ne sont accessibles à l'assistant que si un administrateur l'a autorisée dans Platform settings → Assistant IA.
