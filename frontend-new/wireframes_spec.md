# CNP Wireframes Spec
> Session wireflows du 19 juin 2026. Référence pour l'implémentation frontend.

---

## Shell topnav

### Structure
- Topbar fixe, hauteur 52px, trois zones horizontales
- Zone gauche : scope switcher (icône/avatar + nom + chevron)
- Zone centre (flex:1) : nav primaire, items selon le scope
- Zone droite : search (global, cross-scope) + bell (notifications) + avatar user

### Scope switcher
- Dropdown unique, stratifié :
  - Section "Groupes" : liste des groupes de l'utilisateur, item actif coché
  - Divider + Section "Administration" : visible uniquement si `is_admin=true`
  - Entrée "Plateforme" avec icône server + badge `admin`
- Si 1 seul groupe : badge non-interactif (pas de chevron, pas de dropdown)
- Si 0 groupe : frame onboarding spéciale (reporté S2)

### Nav selon le scope

| Scope | Items nav |
|---|---|
| Groupe | Home / Apps / Settings |
| Plateforme (admin) | Clusters / FinOps / Apps / Settings |

### Zone droite
- Search : global cross-scope, "search in CNP"
- Bell : notifications group-aware
- Avatar : user courant, initiales

---

## Page Apps (scope groupe)

### URL
`/groups/:slug/apps`

### Structure
- Header : titre "Apps" + sous-titre count + bouton filtre + CTA "New app"
- Corps : liste ou grid 4 colonnes (non tranché définitivement)

### Card / ligne app
- Icône app (docker par défaut)
- Nom (font-weight 500)
- Origine : `scaffold` / `onboard` / `import` (texte secondaire, pas de badge coloré)
- Statut : point coloré + label (Healthy / Deploying / Unhealthy / Stopped / Provisioning)
- Timestamp dernière activité

### États
- État vide : illustration + texte + CTA "New app" centré

### Interactions
- Clic sur une app (tout état) → détail app `/groups/:slug/apps/:app-slug`

---

## Stepper /apps/new

### URL
`/groups/:slug/apps/new`

### Structure
Stepper 4 étapes, barre de progression en haut avec états (actif / complété / à venir)

### Étape 1 — Identité
- Choix origine : deux cards cliquables (Scaffold / Onboard), sélection visuellement distincte
- Champ nom d'affichage + preview slug en temps réel (`slugify_app_name()`)
- Si Scaffold : dropdown framework
- Si Onboard : sélecteur repo GitLab existant
- Boutons : Annuler / Suivant

### Étape 2 — Services
- Catalogue de features optionnelles (cards cochables)
  - Chaque feature cochée s'expande inline pour afficher ses options
  - Catalogue extensible sans changer le layout
- Features S1 : Base de données (PostgreSQL), Authentification (Keycloak), Cache (Redis)
- Boutons : Précédent / Suivant

### Étape 3 — CI & Déploiement
- Trigger de déploiement : radio cards (Sur chaque commit / Sur tag)
- Advanced options collapsible (fermé par défaut) :
  - Variables d'env
  - Nombre de replicas
  - Cluster cible
- Note : tout configurables post-création depuis le détail app
- Boutons : Précédent / Suivant

### Étape 4 — Recap
- Résumé groupé par section (Identité / Services / CI & Déploiement)
- Chaque section affiche les valeurs saisies
- Bouton final : "Créer l'application"
- Après soumission → redirection vers détail app état `provisioning`

---

## Page détail app

### URL
`/groups/:slug/apps/:app-slug`

### Structure
- App header (sous le topbar) : icône + nom + statut + metadata (origine · framework · groupe) + actions (lien GitLab + menu "···")
- Onglets : Overview / Deployments / Logs / Settings
- Contenu selon l'onglet actif

### Enum statuts
`healthy` / `deploying` / `updating` / `unhealthy` / `stopped`

### Bandeau alerte
- Affiché uniquement si `unhealthy`
- Contenu : description de l'erreur + lien "Voir les logs"

---

### Onglet Overview

- Métriques runtime (4 cards) : CPU / RAM / Replicas / Uptime
- Grille 2 colonnes :
  - Déploiement courant : commit hash, branche, timestamp, cluster, trigger
  - Services injectés : liste avec statut par service + port exposé

---

### Onglet Deployments

- Liste des déploiements (colonnes : icône statut / commit hash + message / branche / timestamp + durée / tag "courant")
- Clic sur une ligne → expand inline :
  - Auteur, trigger, image tag complète
  - Bouton "Voir le pipeline" → lien externe GitLab (escape hatch)
- Statuts : success (check plein) / failed (x) / in-progress (loader)

---

### Onglet Logs

- Barre de contrôles :
  - Sélecteur pod (dropdown)
  - Filtres niveau : ALL / INFO / WARN / ERROR
  - Search dans les logs
  - Bouton Live (toggle pause scroll)
  - Bouton Export raw (téléchargement fichier brut)
- Flux structuré : colonnes timestamp / niveau / message (font-mono)
- Ligne ERROR : fond légèrement teinté pour visibilité
- Footer : résumé filtre actif + indicateur Live
- Source : Loki, label `app=:app-slug`

---

### Onglet Settings

- Section Identité : nom d'affichage (éditable) + slug (read-only, immuable) + description
- Section Variables d'env : liste clé/valeur, ajout/suppression, valeurs masquables (eye-off), note "Les modifications déclenchent un redeploy"
- Pas de danger zone pour S1 (suppression app : à ajouter S2)

---

## Page Home (scope groupe)

### URL
`/groups/:slug`

### Structure
- Titre groupe + sous-titre (count apps + count membres)
- Ligne métriques (4 cards) : CPU agrégé / RAM agrégée / Apps par statut / Deployments 7j
- Grille 2 colonnes :
  - Activité récente : flux d'événements (deploy success/failed, provisioning, replica en échec, membre ajouté) avec icône + description + timestamp
  - Membres : liste avec avatar/initiales + nom + email + rôle + lien "Gérer" → Settings

---

## Page Settings groupe

### URL
`/groups/:slug/settings`

### Structure
- Section Identité : nom du groupe (éditable) + bouton Sauvegarder
- Section Membres :
  - Formulaire invitation : input username/email GitLab + dropdown rôle + bouton Inviter
  - Liste membres : avatar + nom + email + dropdown rôle inline + icône trash
    - Owner : trash désactivé (opacité réduite, non-cliquable)
    - Membres actifs : rôle modifiable via dropdown inline (save automatique)
  - Invitations en attente : avatar horloge + email + badge "pending" + icône x (annuler)

### Rôles disponibles
Viewer / Developer / Maintainer / Owner (dérivés des access levels GitLab, ADR-0013/0014)

---

## Admin — Clusters

### URL
`/admin/clusters`

### Structure
- Titre + sous-titre (count clusters)
- Grid 2 colonnes, une carte par cluster

### Carte cluster
- Header : icône (cloud = AKS managé, server = k3s self-managed) + nom (font-mono) + statut + provider · région · type
- Métriques (3 colonnes) : Nodes actifs / CPU utilisé·total / RAM utilisée·totale
- Infos techniques : version K8s + type (Public·managed / Privé·IaaS) + pods actifs
- Namespaces par groupe : liste nom namespace (font-mono) + count apps + count pods

### Clusters S1
- `cnp-aks` : Azure, Sweden Central, AKS managed, public
- `cnp-k3s` : Oracle Cloud, Frankfurt, k3s self-managed, privé IaaS

---

## Admin — FinOps

### URL
`/admin/finops`

### Structure
- Titre + sélecteur période (mois)
- Ligne KPIs (4 cards) : Coût total mois / Coût AKS / Coût k3s / Crédits restants + estimation jours
- Grille 2 colonnes :
  - Gauche : barre de progression crédits Azure + breakdown par cluster (barres horizontales)
  - Droite : breakdown par groupe, expandé par app avec coût individuel

### Données
- k3s Oracle = $0.00 (Free Tier) — argument multi-cloud fort pour le jury
- `cnp-system` inclus dans le breakdown (ArgoCD + prometheus-stack)
- Mock data assumée pour S1

---

## Admin — Apps (vue cross-team)

### URL
`/admin/apps`

### Structure
- Titre + sous-titre (count apps · toutes équipes)
- Filtres : bouton Filtrer + dropdown "Tous les groupes"
- En-tête colonnes : Statut / Nom / Groupe / Cluster / Origine
- Liste tabulaire (pas de grid) :
  - Point statut coloré
  - Nom app
  - Groupe (nom équipe)
  - Cluster (font-mono)
  - Origine (scaffold / onboard / import)

---

## Admin — Settings plateforme

### URL
`/admin/settings`

### Structure
- Section Paramètres globaux : nom plateforme + URL publique + bouton Sauvegarder
- Section Connexion GitLab :
  - Badge statut connexion (Connecté / Déconnecté)
  - URL instance GitLab + groupe racine + token service account (masqué, eye-off)
  - Note : dernière vérification + scopes du token
  - Bouton "Tester la connexion" (action synchrone) + bouton Sauvegarder
- Section Enregistrer un cluster :
  - Champ nom + champ endpoint API (vérifié avant enregistrement) + textarea kubeconfig (chiffré au stockage)
  - Note : "Le kubeconfig est stocké chiffré. Seul le contexte actif est utilisé."
  - Bouton "Enregistrer le cluster"

---

## Décisions transversales

- **Slug immuable** : affiché en read-only sous le champ nom partout où il apparaît
- **Settings "App" vs Settings "Groupe"** : pas de renommage, la hiérarchie topbar/onglets suffit à distinguer les deux niveaux visuellement
- **Escape hatch GitLab** : lien externe sur les pipelines CI depuis l'onglet Deployments, pas de duplication du détail CI dans CNP
- **Inline expand** : pattern utilisé sur Deployments (détail déploiement) et Services (options feature)
- **Advanced options collapsible** : env vars / replicas / cluster cible fermés par défaut dans /apps/new
- **Statut provisioning** : valeur de l'enum de santé, pas un état de page séparé
- **Notifications** : group-aware, scope-agnostiques dans le topbar
- **Search** : global cross-scope, même instance dans les deux scopes
