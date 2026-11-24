# CNP Doctor — diagnostiquer une application en panne

Quand une application tombe en panne après un déploiement, CNP Doctor rassemble les signaux
que la plateforme lit déjà (ArgoCD, Kubernetes, logs Loki, pipeline GitLab, événements CNP),
relie la panne au déploiement responsable et propose la correction, le plus souvent un retour
à la dernière version saine.

Trois principes :

- **Le verdict est décidé par la plateforme**, pas par l'IA. L'IA (le provider de l'assistant,
  Platform → Settings → Assistant IA) rédige l'explication à partir de preuves numérotées
  qu'elle ne peut que citer.
- **Les preuves affichées viennent de la plateforme.** Une preuve inventée par l'IA ne peut pas
  apparaître sur la carte.
- **Le Doctor n'exécute rien.** Il propose une action ; un maintainer la confirme dans
  l'interface.

Le Doctor s'adresse aux membres d'une application de rôle **developer ou plus** : developer
pour comprendre la panne, maintainer pour appliquer le rollback.

## Où le trouver

- Page d'une application → onglet **Overview** → carte **CNP Doctor** → choisir l'environnement
  (**prod** / **dev**) → **Diagnostiquer**. Si un seul environnement est en erreur, il est
  présélectionné.
- Bandeau « The application is in error » en haut de la page d'une application →
  **Diagnostiquer** : l'onglet Overview s'ouvre, la carte s'affiche et le diagnostic de
  l'environnement en erreur démarre.
- Cartes **Production environment** / **Dev environment** en état Degraded ou Missing (onglet
  Overview) → **Diagnostiquer**.
- Panneau de l'assistant en mode **Doctor** (interrupteur Assistant / Doctor) → bouton de
  diagnostic de chaque environnement ; le résultat s'affiche dans le fil et sur la carte.
- Ligne de commande : `cnp app doctor <id>` (voir plus bas).

La carte n'apparaît que si l'assistant IA est activé sur la plateforme. Si un administrateur a
restreint l'accès IA aux applications sélectionnées (Platform → Settings → Assistant IA),
l'application doit faire partie de la sélection.

## Le parcours, de la panne au retour à la normale

1. **Panne** : après un déploiement, le bandeau « The application is in error » apparaît et le
   robot de l'assistant passe en mode docteur.
2. **Diagnostiquer** : depuis la carte, le bandeau, une carte d'environnement, le panneau ou la
   CLI.
3. **Collecte** : la plateforme lit ses sources en parallèle, avec un délai maximal par source.
   Une source qui ne répond pas est listée dans « signaux manquants » au lieu de faire échouer
   le diagnostic. Sources lues : statut et historique des déploiements ArgoCD, pods, conteneurs
   et événements Kubernetes, lignes d'erreur des logs de la dernière heure (Loki), dernier
   pipeline GitLab, événements CNP (déploiement, rollback, dégradation), état arrêté de
   l'environnement, statut du cluster.
4. **Règles** : la plateforme décide le verdict, calcule la chronologie, construit le registre
   de preuves (E1, E2…) et la liste des actions possibles (A1, A2…), avec les droits de
   l'utilisateur. Sur les cas évidents (application saine, arrêtée, cluster hors ligne…), la
   réponse s'arrête là, **sans IA**.
5. **IA** : un seul appel au provider. L'IA reçoit le verdict, la chronologie, les preuves
   numérotées et les actions possibles ; elle renvoie un constat, une explication, une cause
   avec sa confiance, les identifiants des preuves retenues et un commentaire par action.
6. **Vérification** : un identifiant de preuve ou d'action inconnu est ignoré ; sans preuve
   valide citée, la confiance est forcée à « faible ». Le verdict, la chronologie, les actions,
   leur ordre et leurs cibles restent ceux de la plateforme.
7. **Carte** : le résultat s'affiche dans l'onglet Overview (et dans le panneau de
   l'assistant).
8. **Rollback confirmé** : un maintainer clique sur « Revenir à la version … » ; une
   confirmation nomme la version cible et l'environnement, puis la plateforme lance le rollback
   existant (le même que l'onglet History). Un developer voit le bouton désactivé avec le rôle
   requis et peut copier une demande prête à transmettre à un maintainer.
9. **Retour à la normale** : ArgoCD redéploie la version saine. Relancer le diagnostic : le
   verdict devient « Application saine ».

### Comment la chronologie relie la panne à un déploiement

- Début de la panne : premier signal d'échec après le dernier déploiement (événement Warning
  Kubernetes, ligne d'erreur, démarrage d'un pod en échec ou dégradation signalée par CNP).
- Corrélation **haute** : la panne commence au plus 10 minutes après le déploiement, et la
  version précédente a tourné au moins 30 minutes sans dégradation. **Moyenne** : jusqu'à
  60 minutes. **Faible** : jusqu'à 6 heures. Au-delà, aucune corrélation : le verdict est « En
  panne » et le rollback n'est pas l'action principale.
- Dernière version saine : le déploiement précédent dont l'image diffère de celle en
  service. C'est la cible du rollback proposé. Sa durée de service s'arrête au déploiement
  qui l'a remplacée.
- Versions : le tag d'image lu dans `values-<env>.yaml` du dépôt GitOps pour chaque entrée
  de l'historique ArgoCD. Une resynchro qui garde la même image n'est pas un nouveau
  déploiement.
- Seules les dégradations de l'environnement diagnostiqué comptent, et seul le pipeline de
  la branche qui l'alimente (`main` pour la prod, `release-dev-*` pour le dev) est lu.
- La confiance affichée pour la cause ne dépasse jamais la corrélation calculée.

## Lire la carte

- **Verdict et constat** : l'état en quelques mots, puis le constat en une phrase.
- **Source** : « IA encadrée » (explication rédigée par l'IA puis vérifiée par la plateforme),
  « Sans IA » (cas évident tranché par la plateforme), « IA indisponible — diagnostic établi
  par la plateforme » (l'IA n'a pas répondu : quota, erreur ou limite atteinte).
- **Cause probable et confiance** : haute, moyenne ou faible. La confiance n'est jamais
  supérieure à ce que les preuves permettent.
- **Chronologie** : les derniers déploiements de l'environnement, le premier signal d'échec,
  la dégradation et un pipeline en échec, dans l'ordre. Le déploiement suspect et la dernière
  version saine sont marqués, avec le délai entre le déploiement et la panne.
- **Preuves** : les preuves retenues par le diagnostic (source, libellé, heure, détail comme
  des lignes de log ou un message Kubernetes, lien). Les autres signaux collectés restent
  accessibles dans une section repliée.
- **Ce qui a changé** : les commits (20 au plus) et les fichiers modifiés (50 au plus) entre la
  dernière version saine et la version en panne, avec un lien de comparaison GitLab. Si
  GitLab refuse l'accès ou si l'application n'a pas de projet GitLab, la carte affiche
  « comparaison indisponible » et la raison ; le reste du diagnostic est complet.
- **Actions** : dans l'ordre conseillé, la première étant l'action principale. Une action non
  autorisée pour le rôle de l'utilisateur est désactivée et indique le rôle requis. Les autres actions ouvrent
  l'onglet Logs, l'onglet History, le pipeline ou la comparaison GitLab.
- **Autres boutons** : relancer le diagnostic, « Copier le diagnostic » (résumé lisible à coller
  dans un ticket ou une discussion), « Approfondir avec l'assistant » pour poser des questions
  de suite.

## Verdicts

| Verdict | Signification | Appel IA | Action principale |
|---|---|---|---|
| Application saine (`healthy`) | ArgoCD Healthy, réplicas prêts, aucun conteneur en échec, aucune ligne d'erreur sur la dernière heure, dernier pipeline non en échec | Non | Aucune |
| Environnement arrêté (`stopped`) | Arrêt volontaire (Stop ou arrêt nocturne des environnements dev) | Non | Relancer l'environnement (Resume) |
| Cluster hors ligne (`cluster_offline`) | Le cluster cible ne répond pas : la panne ne vient pas de l'application | Non | Prévenir un administrateur de la plateforme |
| Déploiement en cours (`deploying`) | Un déploiement est en cours et aucun conteneur n'est en échec | Non | Revérifier dans une minute |
| Pas encore déployée (`not_deployed`) | Aucune application ArgoCD ni ressource Kubernetes dans cet environnement, ou aucun cluster cible | Non | Aucune |
| Signaux insuffisants (`inconclusive`) | Ni ArgoCD ni Kubernetes ne répondent, ou leur état ne permet pas de conclure | Non | Réessayer dans une minute |
| Régression après un déploiement (`regression`) | Panne corrélée au dernier déploiement | Oui | Revenir à la dernière version saine |
| En panne (`failing`) | Panne sans déploiement récent corrélé | Oui | Voir les logs (rollback possible, pas principal) |
| Dernier pipeline en échec (`ci_failure`) | L'application tourne, mais la nouvelle version n'est pas déployée | Oui | Ouvrir le pipeline |
| Instable (`unstable`) | En service, mais erreurs dans les logs ou redémarrages | Oui | Voir les logs |

Un conteneur en `CrashLoopBackOff` pendant qu'ArgoCD affiche `Progressing` n'est **pas** un
déploiement en cours : le diagnostic le traite comme une panne.

Quand l'IA ne répond pas sur un verdict qui la demande, la carte affiche « IA indisponible —
diagnostic établi par la plateforme » : constat et cause sont composés par la plateforme, la
chronologie, les preuves et l'action de rollback restent présentes.

## Qui peut faire quoi

| Rôle sur l'application | Peut faire |
|---|---|
| Viewer | Rien : le diagnostic est réservé aux rôles developer et supérieurs (refus 403) |
| Developer | Lancer un diagnostic (carte, bandeau, panneau, CLI) et lire tout le résultat. Le rollback est affiché désactivé avec « maintainer » comme rôle requis ; « Copier la demande » prépare un message pour un maintainer |
| Maintainer | + confirmer le rollback depuis la carte ; relancer un environnement dev arrêté |
| Owner | + relancer l'environnement prod arrêté (même règle que le bouton Resume) |
| Admin plateforme | Toutes les applications |

Les droits sont ceux des routes existantes : la carte appelle la même route de rollback que
l'onglet History (maintainer et plus).

## Ce qui est envoyé au fournisseur IA

Uniquement pour les verdicts qui demandent une interprétation (`regression`, `failing`,
`ci_failure`, `unstable`), en un seul message, après masquage des secrets (un jeton présent
dans un log n'atteint ni le provider ni la réponse) :

- le nom de l'application, l'environnement et le verdict de la plateforme ;
- la chronologie : révision suspecte, heures, délai avant la panne, durée de service de la
  version précédente, niveau de corrélation ;
- les preuves numérotées : libellés et détails (messages Kubernetes, lignes d'erreur des logs,
  fin du log d'un job CI en échec) ;
- les **titres de commits** et les **noms de fichiers modifiés** entre les deux versions
  (validé par le PO le 2026-11-16) ;
- les actions possibles et les signaux manquants ;
- l'email de l'utilisateur, pseudonymisé pour un provider hors UE
  (`AI_MASK_PII_FOR_NON_EU_PROVIDERS`).

Jamais envoyé : le **contenu du code** (aucun diff), les valeurs des variables
d'environnement, les secrets, les kubeconfigs. Sur un cas évident, rien n'est envoyé.

## Ce que le Doctor ne fait jamais

- Il n'exécute aucune action : ni rollback, ni Resume, ni redéploiement. Il propose ; un
  humain confirme dans l'interface, avec ses propres droits.
- L'IA ne décide pas du verdict, ne crée pas de preuve et n'ajoute pas d'action.
- Il ne se déclenche pas tout seul : un diagnostic est toujours lancé par un utilisateur.
- Il ne conserve pas d'historique des diagnostics. Chaque diagnostic est inscrit dans le
  journal d'audit (Platform → Audit, action `ai_assistant.diagnose`, avec l'environnement, le
  verdict et la source).

## Le robot : mode Assistant et mode Doctor

Le panneau de l'assistant (mascotte en bas à droite ou bouton **AI Assistant** de la sidebar)
a deux modes, choisis avec l'interrupteur **Assistant / Doctor** du panneau :

- **Assistant** : le chatbot habituel.
- **Doctor** : le robot porte une blouse et un stéthoscope, le panneau s'intitule « CNP
  Doctor ». Sur la page d'une application, il propose de diagnostiquer chaque environnement et
  affiche le résultat dans le fil, avec les mêmes actions que la carte. Hors d'une
  application, il invite à en ouvrir une. Une question tapée librement est traitée comme en
  mode Assistant.

Le changement de mode joue une courte animation de changement de tenue (un simple fondu si le
système demande de réduire les animations). Si un administrateur a masqué le robot graphique,
l'interrupteur reste disponible.

Bascule automatique :

- le robot passe en mode **Doctor** quand un diagnostic est lancé, ou à l'ouverture d'une
  application en erreur ;
- un choix fait à la main avec l'interrupteur est respecté tant que l'utilisateur reste sur
  cette application ;
- en quittant les pages de l'application, le robot revient en mode **Assistant** et le choix
  manuel est oublié.

## Ligne de commande

```bash
cnp app doctor 7                 # environnement prod (par défaut)
cnp app doctor 7 --env dev       # ou -e dev
cnp app doctor 7 -o json         # le JSON brut du diagnostic, pour un script
```

L'identifiant numérique de l'application est donné par `cnp app list`. La sortie texte reprend
la carte : verdict, constat, source, cause et confiance, explication, preuves citées,
chronologie, ce qui a changé, actions, signaux manquants. La dernière ligne rappelle que **la
CLI n'exécute aucune action** et indique où appliquer l'action conseillée (pour un rollback :
la version cible et l'onglet History de l'application dans l'interface web).

`--env` n'accepte que `prod` ou `dev` : une autre valeur est refusée avant tout appel réseau.
Une erreur de l'API (rôle insuffisant, assistant désactivé, application inconnue) est affichée
et la commande sort avec le code 1.

## Limites

- **Corrélation n'est pas preuve.** Une panne qui suit un déploiement est probable, pas
  certaine. La confiance est affichée et plafonnée par le calcul (une version précédente trop
  brève ou déjà dégradée ne donne jamais une corrélation haute).
- **Fenêtre d'observation.** Le Doctor lit les lignes d'erreur de la dernière heure de logs
  et l'état actuel de Kubernetes. La chronologie se limite à l'historique conservé par ArgoCD.
- **Un appel IA par diagnostic**, et seulement quand le verdict le demande. Il compte dans les
  limites de l'assistant (questions par utilisateur, budget journalier de la plateforme).
- **Quota du fournisseur.** La clé Gemini actuelle est en offre gratuite (5 requêtes par
  minute, 20 par jour et par modèle). Au-delà, ou si le provider échoue, la carte passe en
  « IA indisponible — diagnostic établi par la plateforme » et reste utilisable.
- **Comparaison des commits.** Elle passe par le jeton GitLab du bot ; si ce jeton n'a pas le
  droit de lire le projet, la carte affiche « comparaison indisponible ».

## Labo de démo local

Pour rejouer le scénario complet (application saine, déploiement cassé, diagnostic, rollback,
retour à la normale) sans toucher un vrai cluster ni le Vault partagé, voir le labo de démo
décrit dans `scripts/doctor-lab/README.md`, à la racine du dépôt.

## Pour les contributeurs

- API : `POST /api/v1/apps/{app_id}/doctor/diagnose`, corps `{"env": "prod" | "dev"}`
  (défaut `prod`). Réponses : 200 (diagnostic), 403 (rôle insuffisant ou application non
  autorisée), 404 (application inconnue), 422 (environnement invalide), 503 (assistant
  désactivé). Usage IA de type `incident` enregistré seulement quand le provider est appelé.
- Code : `backend/services/doctor_signals.py` (collecte), `backend/services/doctor_rules.py`
  (verdict, chronologie, preuves, actions), `backend/services/doctor_service.py` (appel IA,
  vérification, repli), `backend/api/routes/doctor.py` (route et contrat de réponse),
  `frontend-new/src/types/doctor.ts`, `frontend-new/src/store/doctor.ts`,
  `cli/commands/apps.py` (commande `doctor`).
- Conception et spécifications : `openspec/changes/cnp-doctor/`. Choix de la direction IA :
  [ADR-0031](../adr/0031-direction-ia-cnp-doctor.md).
