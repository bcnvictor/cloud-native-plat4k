# ADR-0013 : Migration vers GitLab.com SaaS (free tier)

## Statut

Accepted : 2026-06-03
Supersedes ADR-0003, ADR-0011

## Contexte

ADR-0003 avait retenu `gitlab.cri.epita.fr` (instance GitLab EE de l'EPITA) comme forge Git pour la phase 1. Cette instance présentait un avantage immédiat (comptes EPITA existants, runners partagés, registry incluse) mais une contrainte structurelle : l'accès est conditionné au statut étudiant actif et ne peut pas être garanti au-delà de juin 2026.

Par ailleurs, ADR-0011 documentait l'utilisation d'un PAT personnel faute de Group Access Token, dette directement liée à l'absence de droits admin sur l'instance EPITA.

La migration était prévue. Elle a été anticipée en juin 2026 pour sécuriser la continuité du projet avant la soutenance.

## Décision

Nous avons décidé de migrer vers **GitLab.com free tier** (`https://gitlab.com`) avec un namespace de groupe dédié CNP.

Les variables d'environnement impactées :

```
GITLAB_BASE_URL=https://gitlab.com
GITLAB_BOT_TOKEN=<nouveau PAT gitlab.com>
GITLAB_BOT_NAMESPACE=<namespace groupe CNP>
```

Light changement de code — l'externalisation en variables d'environnement prévue dans ADR-0003 a rendu la migration transparente, minus quelques hardcodes.

## Conséquences

Positif :
- Aucune dépendance au statut étudiant EPITA — continuité garantie post-juin 2026
- Namespace groupe CNP propre, découplé du namespace personnel `victor.biancini`
- API GitLab identique — zéro régression fonctionnelle
- Container registry `registry.gitlab.com` disponible sans configuration supplémentaire

Négatif / Dette :
- Free tier limité à 5 membres par groupe — contournable en mettant le top-level group publique
- PAT personnel toujours utilisé (Group Access Token réservé au tier Premium) — création d'un account bot pour la cnp pour rendre ça propre
- Shared runners GitLab.com soumis à un quota de 400 min/mois sur le free tier

Neutre :
- Les webhooks sortants (pipeline → CNP) fonctionnent de la même façon sur gitlab.com
- La migration GitOps (ArgoCD/Flux) vers la nouvelle URL est scriptable en moins d'une heure
