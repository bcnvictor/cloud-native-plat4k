# Labo de démo CNP Doctor

Rejoue en local, à volonté, le scénario de panne du Doctor : une application saine,
un déploiement qui casse tout, un diagnostic qui désigne le coupable, un rollback
confirmé dans l'interface, et le retour à la normale.

## Ce que c'est, ce que ce n'est pas

- **C'est** une stack Compose séparée (projet `cnp-doctor-lab`) : la vraie interface, le
  vrai backend, une base et un Vault propres au labo, et un serveur simulé
  (`lab_server.py`, bibliothèque standard Python) qui imite ArgoCD, l'API Kubernetes,
  Loki, GitLab et un fournisseur IA compatible OpenAI.
- **Ce n'est pas** un cluster : aucun pod ne tourne. Les réponses sont inventées et
  calculées par rapport à « maintenant » ; seul le scénario `demo-shop` est simulé.
- Le labo ne lit ni n'écrit le Vault partagé, ne touche ni à ta base locale
  habituelle ni à un dépôt ou un cluster réel.

## Prérequis

- Docker avec Compose v2.24.4 ou plus récent (balise `!override`).
- Ports libres sur 127.0.0.1 : **8088** (interface), **8008** (API), **9009** (serveur simulé).
- Rien d'autre : ni clé d'API, ni accès au réseau de l'école.

## Démo pas à pas

1. **Démarrer** (premier lancement : quelques minutes de build)

   ```bash
   ./scripts/doctor-lab/start.sh
   ```

   Le script construit et lance la stack, attend l'API, charge les données de démo
   et remet le scénario à l'état sain.

2. **Se connecter** sur <http://localhost:8088> avec `maintainer@cnp.local` / `maintainer`.

3. **Ouvrir demo-shop** (équipe Team Demo) : l'application est saine en prod sur la
   version `a1b2c3d4`. Un diagnostic à ce stade répond « application saine », sans IA.

4. **Casser l'application**

   ```bash
   ./scripts/doctor-lab/break.sh
   ```

   La version `f4e5d6c7` est déployée en prod, datée de 3 minutes plus tôt pour que la
   boucle de crash ait déjà un historique. Elle lit une variable `PAYMENT_API_URL` qui
   n'existe pas en prod : pods en `CrashLoopBackOff`, ArgoCD `Degraded`, traces
   `KeyError: 'PAYMENT_API_URL'` dans les logs. En dev, la même version tourne
   normalement : la variable y est définie.

5. **Diagnostiquer** (environnement prod) : verdict `regression`, corrélation haute,
   déploiement suspect `f4e5d6c7`, dernière version saine `a1b2c3d4`, deux commits et
   trois fichiers modifiés. La cause citée est la variable manquante. Une ligne de log
   contient un faux jeton : il apparaît masqué (`[REDACTED:gitlab-token]`), ce qui
   montre que les secrets ne partent pas vers l'IA.

6. **Confirmer le rollback** proposé par la carte (« Revenir à la version a1b2c3d4 »).
   Le backend réécrit `image.tag` dans `values-prod.yaml` du dépôt GitOps simulé :
   c'est cette écriture qui fait revenir le labo à l'état sain.

7. **Relancer le diagnostic** : verdict `healthy`. L'historique garde le déploiement
   cassé suivi du rollback.

8. Pour rejouer : `./scripts/doctor-lab/reset.sh`, puis reprendre à l'étape 4.

Les liens « Voir ce qui a changé sur GitLab » et « Ouvrir le pipeline » mènent à des
pages simulées servies par le labo sur <http://localhost:9009>.

## Scénario « échec CI »

```bash
./scripts/doctor-lab/ci-failure.sh
```

L'application tourne normalement sur `a1b2c3d4`, mais le dernier pipeline (#1204) a
échoué au job `test` : `test_apply_promo_code` attend 85,00 € et obtient 90,00 €. Le
diagnostic répond `ci_failure` et propose d'ouvrir le pipeline. Retour avec `reset.sh`.

## Comptes

| Compte                 | Mot de passe | Rôle sur demo-shop                               |
|------------------------|--------------|--------------------------------------------------|
| `admin@cnp.local`      | `admin`      | administrateur de la plateforme                  |
| `maintainer@cnp.local` | `maintainer` | maintainer : diagnostic et rollback              |
| `dev@cnp.local`        | `dev`        | developer : diagnostic, rollback non autorisé    |
| `viewer@cnp.local`     | `viewer`     | viewer : pas de diagnostic                       |

## Scripts

| Script          | Effet                                                                       |
|-----------------|-----------------------------------------------------------------------------|
| `start.sh`      | démarre la stack, charge les données, état sain (`--real-ai` : IA réelle)   |
| `break.sh`      | panne en prod (efface d'abord l'historique plateforme de demo-shop)         |
| `ci-failure.sh` | prod saine, dernier pipeline en échec                                       |
| `reset.sh`      | retour à l'état sain initial                                                |
| `stop.sh`       | arrête le projet `cnp-doctor-lab` ; `stop.sh -v` supprime aussi sa base    |

L'état du scénario se lit sur <http://localhost:9009/lab/state>.

## Utiliser un fournisseur IA réel

```bash
./scripts/doctor-lab/start.sh --real-ai
```

Le backend prend alors `AI_PROVIDER`, `AI_API_KEY`, `AI_MODEL` (et `AI_BASE_URL` si
défini) dans le shell ou le `.env` racine, via `compose.lab.real-ai.yml`. Le labo ne va
jamais chercher la clé dans le Vault partagé : si elle n'est que là, exporte-la dans le
shell avant de lancer. Relancer `start.sh` sans l'option revient au fournisseur simulé.
Attention aux quotas des offres gratuites (Gemini : quelques requêtes par minute et
par jour) : répète la démo avec le fournisseur simulé.

## Garanties de sécurité

- Compose est toujours appelé avec `-p cnp-doctor-lab` et des `-f` explicites :
  `docker-compose.override.yml`, qui branche le backend sur le Vault partagé, n'est
  jamais chargé.
- Le backend vise le Vault du labo (`lab-vault`, mode dev, en mémoire, non publié).
  Au démarrage, `lab-vault-init` y écrit un marqueur dans `secret/cnp/platform` : le
  backend n'écrase donc pas son environnement avec le Vault et n'y recopie pas ses
  réglages.
- Toutes les adresses sortantes du backend (GitLab, GitOps, Loki, Prometheus, IA,
  Keycloak) pointent vers le serveur simulé `doctor-lab` ; Grafana, OAuth GitLab et le
  miroir des membres GitLab sont coupés. Aucune valeur du `.env` n'atteint le backend,
  sauf les quatre variables IA avec `--real-ai`.
- `seed.py` refuse de tourner si le backend n'est pas branché sur le Vault du labo
  (adresse et marqueur vérifiés), si GitLab ou Loki ne visent pas le serveur simulé.
- Base, volumes et réseau appartiennent au projet `cnp-doctor-lab` ; `stop.sh` n'arrête
  que lui. Les ports ne sont publiés que sur 127.0.0.1.

## Dépannage

- **L'API ne répond pas** :
  `docker compose -p cnp-doctor-lab -f docker-compose.yml -f scripts/doctor-lab/compose.lab.yml logs backend`.
- **Port déjà utilisé** (8088, 8008 ou 9009) : libère-le ou modifie `ports` dans
  `compose.lab.yml`. Le port 9000 de l'hôte n'est pas utilisé par le labo.
- **« Kubernetes indisponible » ou « ArgoCD token unavailable » dans le diagnostic** :
  le Vault du labo, en mémoire, a été recréé et a perdu les secrets du cluster.
  Relance `./scripts/doctor-lab/start.sh`.
- **Corrélation « moyenne » au lieu de « haute », ou déploiement affiché comme un
  rollback** : il reste des événements d'une répétition précédente. Utilise
  `break.sh` / `reset.sh`, qui les effacent, plutôt qu'un appel direct à `/lab/break`.
- **`healthy` attendu, `unstable` obtenu** : vérifie l'état sur `/lab/state` ; après
  un rollback il doit valoir `rolled_back`.
- **Le diagnostic n'appelle pas l'IA** : normal pour un verdict sain (règles seules).
  Avec `--real-ai`, une erreur de quota bascule la carte sur le diagnostic de la
  plateforme (`rules_fallback`).
- **Repartir de zéro** : `./scripts/doctor-lab/stop.sh -v` puis `start.sh`.
