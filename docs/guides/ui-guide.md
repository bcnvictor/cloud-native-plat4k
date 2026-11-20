# Guide de l'interface CNP (Plat4k)

Cette page décrit chaque écran de la console web, où trouver chaque fonctionnalité et qui peut l'utiliser. Elle sert de référence à l'assistant Plat4k : en cas de doute, c'est elle qui fait foi sur les menus, onglets et boutons.

## Structure générale de l'écran

- **Barre latérale gauche (sidebar)** : sélecteur de contexte en haut, menu de navigation, bouton **AI Assistant** et menu utilisateur en bas (email, **My profile**, **Sign out**). Elle se replie avec le bouton « Collapse sidebar ».
- **Sélecteur de contexte** (« Sélectionner un groupe ») : liste les groupes GitLab dont l'utilisateur est membre ; un administrateur voit aussi l'entrée **Platform** (badge admin) qui ouvre l'espace d'administration.
- **Barre du haut (TopNav)** : fil d'Ariane (ex. `Team A › Apps › mon-app`) et cloche **Notifications**.
- **Assistant Plat4k** : la mascotte en bas à droite (ou le bouton AI Assistant de la sidebar) ouvre le tiroir de chat. La mascotte peut être masquée par un administrateur ; le bouton de la sidebar reste disponible. Le panneau a deux modes, **Assistant** et **Doctor** (voir « Mode Doctor du panneau de l'assistant »).

## Rôles et permissions

Les rôles viennent de GitLab (appartenance au groupe ou au projet) :

| Rôle CNP | Niveau GitLab | Peut faire |
|---|---|---|
| Viewer | Guest/Reporter | Consulter apps, logs, historique, métriques |
| Developer | Developer | + variables d'environnement **dev** (jamais les clés prod), diagnostic **CNP Doctor** (sans pouvoir confirmer le rollback proposé) |
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
3. **CI & Deploy** : **Target cloud** (cluster cible ; sans cluster enregistré, celui par défaut est utilisé), **Deploy trigger** (**On every commit** sur main, ou **On tag**), **Internet exposure** (sous-domaines `<slug>.cloud-native-plat4k.me` en prod et `dev.<slug>.cloud-native-plat4k.me` en dev ; disponible seulement sur les clusters que le DNS public atteint — aujourd'hui `cnp-aks` —, sinon accès par port-forward), **Advanced options** (variables d'environnement, **Replica count**).
4. **Recap** : vérifier puis **Create app**. L'application passe en statut *onboarding* pendant le provisioning (repo, CI, ArgoCD).

Tout reste modifiable ensuite dans l'onglet Settings de l'application.

## Page d'une application — en-tête et onglets

Chemin : groupe → **Apps** → cliquer sur l'application (`/groups/<groupe>/apps/<app>`).

En-tête : nom, description, lien vers le dépôt source. Si l'application est en erreur, un bandeau « The application is in error » propose d'ouvrir les logs et un bouton **Diagnostiquer** (developer+, assistant IA activé) : depuis n'importe quel onglet, il ouvre l'onglet Overview, affiche la carte **CNP Doctor** et lance le diagnostic de l'environnement en erreur.

Onglets : **Overview**, **Logs**, **History**, **Settings**, **Assistant**.

## Onglet Overview (état, métriques, stop/resume)

- Cartes **CPU** (millicores), **RAM**, **Replicas** (prêts/désirés) et **Last sync**, avec mini-graphes ; lien vers Grafana. « Metrics unavailable » signifie que Prometheus n'est pas joignable.
- Cartes **Production environment** et **Dev environment** : état ArgoCD **Sync** (Synced/OutOfSync), **Health** (Healthy, Progressing, Degraded, Missing, Stopped), **Image** déployée, **Last sync**. Une carte en état **Degraded** ou **Missing** propose **Diagnostiquer**, qui lance CNP Doctor sur cet environnement.
- **CNP Doctor** (si l'assistant IA est activé ; diagnostic réservé au rôle developer ou plus) : diagnostic d'une application en panne. Chemin : onglet **Overview** → carte **CNP Doctor** → sélecteur **prod** / **dev** (l'environnement en erreur est présélectionné) → **Diagnostiquer**. La carte montre les étapes (collecte, chronologie, analyse, vérification), puis le **verdict** et le constat, la **source** (« IA encadrée », « Sans IA » pour un cas évident, ou « IA indisponible — diagnostic établi par la plateforme »), la **cause probable** avec sa confiance, la **chronologie** (déploiement suspect, dernière version saine, délai avant la panne), les **preuves** (les autres signaux dans une section repliée), **ce qui a changé** (commits et fichiers, lien de comparaison GitLab) et les **actions** dans l'ordre conseillé. Action **Revenir à la version …** (maintainer+) : une confirmation nomme la version et l'environnement, puis lance le rollback (le même que l'onglet History) ; un developer voit le bouton désactivé avec le rôle requis et **Copier la demande** pour un maintainer. Autres boutons : relancer le diagnostic, **Copier le diagnostic**, **Approfondir avec l'assistant**. Le Doctor n'exécute jamais rien de lui-même. Guide complet : [CNP Doctor](cnp-doctor.md).
- **Stop / Resume** par environnement (maintainer+) : **Stop** puis **Confirm** met l'environnement à zéro réplica via un commit GitOps (*scale-to-zero*) ; **Resume** le relance. Les environnements dev peuvent aussi être arrêtés automatiquement la nuit (voir « Arrêt nocturne »).
- **Cloud target** : cluster cible, endpoint et statut (online/offline).
- **Quick access** : URLs prod/dev si l'app est exposée, sinon la commande `kubectl port-forward -n dev svc/<slug> 8000:8000` (port local 8000 : une des origines autorisées par le realm Keycloak dev) ; lien **GitLab repository**.
- **Conseiller FinOps IA** (si l'assistant IA est activé) : bouton **Analyser la consommation** — analyse des 24 dernières heures de CPU/RAM (Prometheus), *requests* proposées, coût mensuel réservé → proposé et recommandations de right-sizing (conseils uniquement, à reporter dans le chart Helm). **Approfondir avec l'assistant** poursuit l'analyse dans l'assistant.

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
- **Internet exposure** : interrupteur *Exposed on internet* / *Port-forward only* (maintainer+). Désactivé sur un cluster que le DNS public n'atteint pas, sauf pour couper l'exposition d'une app déjà exposée. Avec Keycloak, les redirect URIs suivent l'exposition ; si leur mise à jour a échoué, un avertissement propose **Retry**.
- Le **cluster cible** n'est pas modifiable ici : il se choisit à la création (New app → étape CI & Deploy → Target cloud).
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
- **conseille sur les coûts** d'une application (« mon app est-elle bien dimensionnée ? », « comment réduire ses coûts ? ») : consommation des 24 dernières heures, *requests* proposées et économie mensuelle possible ;
- **diagnostique** une application en erreur (rôle developer ou plus) : dernières lignes ERROR des logs, état des pods Kubernetes (redémarrages, CrashLoopBackOff, OOMKilled) et dernier pipeline CI en échec avec la fin de son log. Pour un diagnostic complet et vérifié (chronologie, preuves, rollback proposé), utiliser **CNP Doctor** : carte de l'onglet Overview ou mode **Doctor** du panneau ;
- explique où trouver une fonctionnalité et comment l'utiliser, à partir de cette documentation ;
- ne fait aucune action : il ne déploie pas, n'arrête pas, ne modifie rien — il indique le bouton à utiliser ;
- adapte ses réponses au profil de l'utilisateur sur la page ouverte : **viewer** (réponse courte, orientée impact), **developer** (diagnostic technique, noms des variables dev), **maintainer/owner** (diagnostic + actions possibles, variables prod), **admin** (vue plateforme : clusters, anomalies, usage IA). Il ne montre jamais plus que ce que l'utilisateur peut voir dans l'interface ;
- peut être lancé en un clic avec les boutons **Expliquer avec l'IA** : bandeau « The last CI pipeline failed » en haut d'une application, bouton **Expliquer les erreurs** de l'onglet Logs quand des lignes ERROR sont affichées (le bandeau « The application is in error » et les cartes d'environnement **Degraded** / **Missing** proposent **Diagnostiquer**, qui lance CNP Doctor) ;
- est limité à quelques questions par minute et par jour par utilisateur, et à un budget journalier pour la plateforme ; un message l'indique quand une limite est atteinte.

Les détails d'une application (événements, statut ArgoCD, métriques, coûts) ne sont accessibles à l'assistant que si un administrateur l'a autorisée dans Platform settings → Assistant IA.

## Mode Doctor du panneau de l'assistant

Le panneau de l'assistant a un interrupteur **Assistant / Doctor** (utilisable au clavier) :

- **Assistant** : le chat décrit ci-dessus.
- **Doctor** : le robot porte une blouse et un stéthoscope et le panneau s'intitule « CNP Doctor ». Sur la page d'une application, il propose de diagnostiquer chaque environnement (prod, dev) et affiche le résultat dans le fil, avec les mêmes actions que la carte **CNP Doctor** de l'onglet Overview (un diagnostic lancé d'un côté apparaît de l'autre). Hors d'une application, il invite à en ouvrir une. Une question tapée librement reçoit la même réponse qu'en mode Assistant.
- **Bascule automatique** : le robot passe en mode Doctor quand un diagnostic est lancé ou quand l'utilisateur ouvre une application en erreur. Un choix fait à la main avec l'interrupteur est respecté tant que l'utilisateur reste sur cette application ; en quittant les pages de l'application, le robot revient en mode Assistant.
- Le changement de mode joue une animation de changement de tenue (un fondu si le système demande de réduire les animations). Si le robot graphique est masqué par un administrateur, l'interrupteur reste disponible.

Pour diagnostiquer une application en ligne de commande : `cnp app doctor <id> --env prod|dev` (voir la référence CLI).
