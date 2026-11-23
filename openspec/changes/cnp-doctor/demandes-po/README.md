# Demandes au PO — CNP Doctor

Ce dossier liste les autorisations et les accès dont le travail sur CNP Doctor a besoin et
que le développeur ne peut pas obtenir seul. Aucune demande n'arrête le développement :
chaque ligne dit ce qui fonctionne sans. Cocher une demande quand la réponse est obtenue, et
noter la date et la trace (message, ticket, compte rendu).

| # | Demande | Pourquoi | À qui | Bloquant ? | Ce qui marche sans |
|---|---|---|---|---|---|
| 1 | Lecture des commits par le jeton GitLab du bot | « Ce qui a changé » appelle l'API de comparaison GitLab sur les projets des applications | PO → administrateur du groupe GitLab des applications | Non | Tout, sauf la liste des commits : la carte affiche « comparaison indisponible » |
| 2 | Clé d'API Mistral (ou autre provider sans plafond journalier) | La clé Gemini gratuite (5 requêtes/min, 20/jour par modèle) ne suffit pas pour répéter la démo | PO | Non | Le repli sans IA garde la carte utile ; le labo de démo utilise un provider simulé |
| 3 | Application et droits pour répéter la démo sur un vrai cluster | Montrer le scénario de bout en bout ailleurs qu'en local | PO → owner du groupe GitLab concerné | Non | Le labo de démo local (`scripts/doctor-lab/`) |
| 4 | Validation de gouvernance écrite | Trace de l'accord oral du 2026-11-16 sur ce qui part chez le provider IA, et sur les droits | PO | Non pour développer | Le comportement actuel suit l'accord oral |
| 5 | Ticket Linear pour la fonctionnalité | La branche s'appelle `feature/cnp-doctor` faute de ticket ; convention `feature/4k-NNN-…` | PO | Non | Le travail continue sur `feature/cnp-doctor` |
| 6 | Relecture de l'ADR-0031 par un autre pôle, et coordination avec la PR #65 | Critère d'acceptation du spike 4K-247 non coché ; section « Transport » de l'ADR | PO → relecteur d'un autre pôle ; auteur de la PR #65 | Non | L'ADR reste « Proposed » |
| 7 | Pousser la branche et ouvrir la PR | Les commits sont uniquement locaux | Le développeur, quand il est prêt | Non | La revue ne peut pas commencer |

## 1. Lecture des commits par le jeton GitLab du bot

- [ ] Obtenu le : _…_ — trace : _…_

**Contexte.** La section « Ce qui a changé » compare la dernière version saine et la version
en panne avec l'API GitLab (`GET /projects/:id/repository/compare`), en utilisant
`GITLAB_BOT_TOKEN`. Le rôle du compte bot et les scopes du jeton sur les projets des
applications n'ont pas été vérifiés.

**À demander.** Confirmer que le compte bot dont le jeton est `GITLAB_BOT_TOKEN` a **au moins
le rôle Reporter** sur les projets des applications, et que le jeton a les scopes
**`read_api`** et **`read_repository`**. Sinon, accorder ces droits.

**Sans réponse.** `changes.unavailable_reason` est renseigné, la carte affiche « comparaison
indisponible » ; verdict, chronologie, preuves et rollback fonctionnent.

**Vérifier ensuite.** Lancer un diagnostic sur une régression : la carte liste les commits et
les fichiers, sans « comparaison indisponible ».

## 2. Clé d'API Mistral

- [ ] Obtenu le : _…_ — trace : _…_

**Contexte.** La clé Gemini du projet est en offre gratuite : 5 requêtes par minute et 20 par
jour et par modèle. Une démo répétée plusieurs fois par jour épuise ce quota. Mistral est déjà
pris en charge par la plateforme (Platform → Settings → Assistant IA → Provider IA).

**À demander.** Une clé d'API **Mistral**, ou d'un autre provider pris en charge sans plafond
journalier, pour les répétitions et la soutenance. Un administrateur plateforme la saisit dans
Platform → Settings → Assistant IA (stockée chiffrée, jamais réaffichée) : la clé n'a pas
besoin de transiter par le développeur.

**Sans réponse.** Quand le quota est atteint, le Doctor répond quand même avec « IA
indisponible — diagnostic établi par la plateforme » (chronologie, preuves, action de
rollback). Le labo de démo fonctionne avec un provider simulé, sans clé.

## 3. Application et droits pour répéter la démo sur un vrai cluster

- [ ] Obtenu le : _…_ — trace : _…_

**Contexte.** Le scénario de démo casse une application par un déploiement, la diagnostique,
puis revient à la version saine par un rollback confirmé par un maintainer.

**À demander.**

- une application **dédiée à la démo**, sur un vrai cluster, que l'on a le droit de casser
  volontairement (déploiement qui plante au démarrage) ;
- le rôle **maintainer** sur son groupe GitLab pour la personne qui fait la démo, afin de
  confirmer le rollback.

**Sans réponse.** Le labo de démo local (`scripts/doctor-lab/`) rejoue le scénario complet
sans toucher un vrai cluster, le dépôt GitOps réel ni le Vault partagé.

## 4. Validation de gouvernance

- [ ] Obtenu le : _…_ — trace : _…_

**Contexte.** Le PO a validé oralement le 2026-11-16 le périmètre du Doctor, dont l'envoi au
provider IA des titres de commits et des noms de fichiers modifiés (jamais le contenu du
code).

**À demander.** Une **trace écrite** (message, commentaire de ticket ou compte rendu) de deux
décisions :

1. les **titres de commits** et les **noms de fichiers modifiés** sont transmis au provider
   IA, jamais le contenu du code ;
2. le diagnostic est **réservé aux rôles developer et supérieurs** sur l'application (un
   viewer reçoit un refus).

**Sans réponse.** Le code suit déjà l'accord oral ; seule la trace manque pour la revue.

## 5. Ticket Linear

- [ ] Obtenu le : _…_ — numéro : _4K-…_

**Contexte.** Aucun ticket n'existe pour la fonctionnalité : la branche s'appelle
`feature/cnp-doctor` au lieu de suivre la convention `feature/4k-NNN-…`. Le choix de la
direction vient du spike 4K-247.

**À demander.** La création d'un ticket Linear pour CNP Doctor (lié au spike 4K-247), pour
nommer la branche et la PR selon la convention.

**Sans réponse.** Le travail continue sur `feature/cnp-doctor` ; la branche pourra être
renommée une fois le ticket créé.

## 6. Relecture de l'ADR-0031 et coordination avec la PR #65

- [ ] Relecteur désigné : _nom, pôle_
- [ ] Section « Transport » vue avec l'auteur de la PR #65

**Contexte.** La relecture de l'ADR-0031 par un membre d'un autre pôle est un critère
d'acceptation du spike 4K-247 ; la case « Relu par » de l'ADR n'est pas cochée. La PR #65
(ticket 4K-77, serveur MCP en lecture seule `cnp-mcp`, ADR-0029) touche le même sujet que la
section « Transport » de l'ADR-0031, mise à jour le 2026-11-17.

**À demander.**

1. qu'un membre d'un **autre pôle** relise l'ADR-0031, pour qu'elle passe de « Proposed » à
   « Accepted » ;
2. un échange avec l'**auteur de la PR #65** pour valider la formulation de la section
   « Transport » : le Doctor passe par l'API REST, et l'exposer comme outil MCP serait une
   suite, hors du périmètre validé.

**Sans réponse.** L'ADR reste « Proposed » ; le développement n'en dépend pas.

## 7. Pousser la branche et ouvrir la PR

- [ ] Branche poussée le : _…_
- [ ] PR ouverte : _#…_

**Contexte.** Les commits de `feature/cnp-doctor` sont uniquement locaux. La branche est
reportée sur `main` du 2026-11-20 (serveur MCP de la PR #65 compris) : elle peut être
poussée telle quelle.

**À faire.** Le développeur pousse la branche et ouvre la PR quand il est prêt (de préférence
après la demande 5, pour nommer la branche selon la convention). Le PO est prévenu pour la
revue.

**Tant que ce n'est pas fait.** Rien n'est visible des autres membres de l'équipe et la revue
ne peut pas commencer.
