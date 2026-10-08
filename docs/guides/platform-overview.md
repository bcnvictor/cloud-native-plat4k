# Vue d'ensemble de la plateforme CNP (capacités & interface)

Cette page résume ce que l'utilisateur peut faire dans la CNP. Le détail écran par écran (boutons, onglets, permissions) est dans le [guide de l'interface](ui-guide.md). Les deux pages servent de référence à l'assistant Plat4k.

## Navigation

### Menu administrateur (plateforme)
- **Clusters** — clusters Kubernetes enregistrés, leur état de santé et le service discovery.
- **Apps** — catalogue des applications gérées par la plateforme.
- **FinOps** — coûts CPU/RAM estimés par groupe et par application sur 30 jours.
- **Users** — gestion des utilisateurs et de leurs rôles.
- **Audit** — journal d'audit des actions (traçabilité).
- **Settings** — configuration de la plateforme (voir ci-dessous).

### Menu d'un groupe
- **Home** — tableau de bord du groupe.
- **Apps** — applications du groupe.
- **Metrics** — métriques du groupe.
- **Settings** — réglages du groupe.

### Détail d'une application (onglets)
- **Overview** — état, métadonnées, résumé de l'application.
- **Logs** — journaux de l'application.
- **History** — historique des événements et déploiements.
- **Settings** — identité, variables d'environnement dev/prod, exposition internet, suppression.
- **Assistant** — réglages IA de l'application et chat IA contextualisé sur cette application.

## Le menu Settings (plateforme)

La page **Settings** administrateur (« Platform settings ») regroupe les paramètres/réglages/options de la plateforme. Elle contient **quatre sections** :

1. **Global settings** (paramètres généraux)
   - **Platform name** — nom affiché de la plateforme.
   - **Public URL** — URL publique de la plateforme.
2. **Assistant IA** (paramètres du chatbot IA, réglables globalement)
   - **Activer l'assistant IA** — active ou coupe le chatbot sur toute la plateforme.
   - **Afficher le bot graphique** — affiche ou masque la mascotte flottante.
   - **Accès aux données de la CNP** — case à cocher : autorise l'assistant à répondre à partir de la documentation et des données de la plateforme.
   - **Accès aux données d'une application / repo GitLab** — case à cocher + liste d'applications à sélectionner : autorise l'assistant à lire les métadonnées des applications choisies (selon les permissions de l'utilisateur).
   - **Provider IA (souveraineté)** — choix du fournisseur : Mock, Mistral (UE), Gemini (US) ou DeepSeek (Chine), avec une info-bulle « i » décrivant les risques de souveraineté et avantages de chacun.
   - **Modèle** — nom du modèle IA à utiliser.
   - **Clé API** — clé du provider, masquée et chiffrée au repos.
3. **GitLab connection**
   - **GitLab instance URL** — URL de l'instance GitLab.
   - **Root group** — groupe racine GitLab.
   - **Token service account** — jeton du compte de service (masqué).
   - **Test connection** — vérifie la connexion GitLab.
4. **Register cluster**
   - **Name** et paramètres pour enregistrer un nouveau cluster.

En résumé, les options/paramètres du menu Settings de la plateforme sont : le nom de la plateforme, l'URL publique, les réglages de l'Assistant IA (activation, mascotte, accès aux données CNP, accès aux applications, provider, modèle, clé API), la connexion GitLab, et l'enregistrement de clusters.

## Réglages de l'assistant IA (par application)

Dans l'onglet **Assistant** d'une application, section « AI Assistant settings » (maintainer ou owner requis) :
- **Activer l'assistant** (`ai_enabled`) — active le chat IA pour cette application.
- **Mode de contexte** — `metadata_only` (par défaut, aucune donnée de code) ou `metadata_and_code` (nécessite d'accepter un avertissement explicite).
- **Scan de sécurité** (`ai_security_scan_enabled`) et **synthèse IA des scans** (`ai_security_summary_enabled`).

## Assistant IA — capacités

- **Assistant global** (mascotte ou bouton de la barre latérale, agent « platform ») : il connaît la page ouverte et consulte en direct, avec les droits de l'utilisateur, l'état des applications, leurs métriques, les coûts, les membres des groupes et l'activité récente ; il s'appuie sur la documentation CNP pour expliquer où trouver et comment utiliser chaque fonctionnalité.
- **Assistant d'application** (onglet Assistant) : questions contextualisées sur une application (statut, événements récents, métriques, coûts).
- **Mode FinOps** : sur une application, l'assistant produit des recommandations chiffrées d'optimisation des coûts (impact estimé en USD sur 30 jours, hypothèse de calcul, niveau de risque et de confiance) à partir des coûts CPU/RAM mesurés. Pour un chiffrage précis, il faut une application avec des données de coût disponibles (labels et métriques Prometheus présents).
- L'assistant **conseille uniquement** : il n'écrit pas dans GitLab, ne déploie pas et ne modifie aucune configuration. Il ne révèle jamais de secret.

## FinOps

La page **FinOps** et le mode FinOps de l'assistant s'appuient sur les coûts estimés à partir des métriques Prometheus : consommation CPU (par cœur·heure) et RAM (par Gio·heure) agrégées sur 30 jours, par groupe et par application. Les recommandations d'optimisation ne sont jamais appliquées automatiquement : toute décision reste validée par l'équipe.
