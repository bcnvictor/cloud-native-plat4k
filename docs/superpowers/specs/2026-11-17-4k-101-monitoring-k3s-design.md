# 4K-101 — Stack monitoring sur k3s Oracle (Tailscale + kube-prometheus-stack + Promtail)

Ticket : [4K-101](https://linear.app/sigl-4k/issue/4K-101/stack-monitoring-sur-k3s-oracle-tailscale-kube-prometheus-stack)
— bloque 4K-102 (branchement backend multi-cluster).
Branche : `feature/4k-101-stack-monitoring-sur-k3s-oracle-tailscale`.

## Intention

`cnp-k3s` (VM Oracle Ampere A1, arm64, 3 OCPU / 20 GB, k3s single-node) fait tourner ArgoCD,
ESO, Reloader et l'opérateur Tailscale, mais n'a ni stack d'observabilité ni route Tailscale
vers ses ClusterIPs. Ce ticket pose les deux pour que :

1. le cluster soit observable depuis le **Grafana central** de `cnp-control` (ADR-0020) ;
2. Prometheus et Loki k3s aient des **ClusterIPs connues et stables**, joignables depuis
   `cnp-control` via Tailscale — c'est l'entrée de 4K-102.

Le résultat doit aligner k3s sur AKS et GKE : mêmes charts, mêmes noms de Services, même
mécanisme réseau, pour que 4K-102 traite les trois clusters de la même façon.

## Objectifs

- `cnp-control` joint n'importe quelle ClusterIP de `cnp-k3s` sans port-forward.
- `kube-prometheus-stack` + `loki-stack` (Loki + Promtail) tournent sur `cnp-k3s`, sans cible
  DOWN permanente, avec les labels CNP (`cnp.io/owner`, `cnp.io/group-id`) exploitables.
- Datasources `Prometheus cnp-k3s` et `Loki cnp-k3s` en état OK dans le Grafana central.
- Runbook reproductible dans `infra/oracle/k3s/README.md`.

## Non-objectifs

- **Pas de branchement backend** : pas de `PUT /clusters/{id}` avec `prometheus_url` /
  `loki_url`, pas de changement de code backend, frontend ou CLI (périmètre 4K-102).
- Pas de Terraform pour la stack monitoring (choix utilisateur : commandes Helm dans le
  README, comme AKS/GKE). Le Terraform existant de k3s (`ingress-nginx`) n'est pas touché.
- Pas de dashboards Grafana nouveaux, pas d'alerting, pas de persistance Prometheus/Loki
  au-delà des défauts des charts (identique AKS/GKE).
- Pas de changement sur AKS ni GKE.

## Anti-objectifs

- Exposer Prometheus/Loki k3s publiquement (LoadBalancer, NodePort, Ingress) : l'ADR-0020
  veut justement sortir de ce modèle.
- Casser l'existant : la datasource par défaut `prometheus-cnp` et les dashboards qui
  l'utilisent, l'egress ESO → Vault porté par l'opérateur Tailscale k3s (4K-105).
- Élargir l'ACL Tailscale au-delà de ce qu'AKS/GKE ont déjà.

## Contexte existant (à lire avant de construire)

| Élément | Où |
|---|---|
| Runbook k3s (install, ArgoCD, ingress) | `infra/oracle/k3s/README.md` |
| Opérateur Tailscale k3s (déjà installé, 4K-105) | `infra/oracle/k3s/tailscale/operator-values.yaml`, `infra/eso/README.md` |
| Modèle Connector | `infra/gke/tailscale/connector.yaml`, `infra/aks/tailscale/connector.yaml` |
| Modèle monitoring | `infra/gke/monitoring-values.yaml`, section 5 de `infra/gke/README.md` |
| ACL Tailscale (Terraform) | `infra/tailscale/main.tf` |
| Grafana central | service `grafana` de `docker-compose.yml` (profil `production`), provisioning `infra/grafana/provisioning/datasources/cnp.yaml` |
| ADRs | 0019 (Tailscale), 0020 (observabilité centralisée), 0024 (ESO egress), 0026 (GKE) |

## Décisions

### 1. Réseau : Connector Tailscale (écart assumé au ticket)

Le ticket demandait `tailscaled` en systemd sur la VM et interdisait l'opérateur. Depuis sa
rédaction, l'opérateur a été installé sur k3s pour l'egress ESO (4K-105) et AKS/GKE
utilisent un `Connector`. **Décision utilisateur : suivre le pattern AKS/GKE.**

- Nouveau `infra/oracle/k3s/tailscale/connector.yaml` : `Connector` `k3s-subnet-router`,
  `hostname: k3s-subnet-router`, `tags: [tag:k8s]`, en-tête de commentaire au format de
  celui de GKE (commande `kubectl apply`, approbation de route).
- Routes annoncées : **`10.43.0.0/16` (Service CIDR) uniquement** — *écart au ticket, mon
  choix* : le ticket demandait aussi le Pod CIDR `10.42.0.0/16`, inutile pour joindre des
  ClusterIPs et absent d'AKS/GKE. Vérifier les CIDR réels :
  `ps aux | grep k3s` / `/etc/rancher/k3s/config.yaml` sur la VM ou
  `kubectl get svc kubernetes -n default` (doit être `10.43.0.1`).
- Collision de CIDR : `10.43.0.0/16` est le Service CIDR par défaut de tout k3s/k3d.
  Avant d'appliquer, vérifier sur `cnp-control` (`ip route`, `tailscale status`) qu'aucune
  route locale ni aucun autre device du tailnet n'utilise déjà cette plage. Les autres
  postes ne sont pas concernés : l'ACL ne donne la route qu'à `tag:cnp-control`. *(Mon
  choix : simple vérification, aucun changement de plan attendu.)*
- Le critère « expiration de clé désactivée » devient sans objet : les devices taggés créés
  par l'opérateur n'expirent pas. Le vérifier dans la console (colonne *Expiry*).
- UDP 41641 intra-VCN : **optionnel**. Sans lui Tailscale passe par DERP (fonctionnel, plus
  lent). Documenter en note dans le README ; l'ouvrir si `tailscale ping` depuis
  `cnp-control` reste en `via DERP`.

**Point de risque** : un pod proxy Tailscale doit pouvoir router vers les ClusterIPs
(flannel + kube-proxy iptables, comme AKS). Si le `curl` de validation échoue alors que la
route est distribuée, investiguer avant de contourner (piste : `tailscale.com/expose` sur
les Services, comme mentionné dans `infra/aks/tailscale/connector.yaml`).

### 2. ACL Tailscale

Dans `infra/tailscale/main.tf`, ajouts calqués sur GKE :

- `autoApprovers.routes` : `"10.43.0.0/16" = ["tag:k8s"]  # Service CIDR k3s`.
- Règle `accept` `src = ["tag:cnp-control"]` vers `10.43.0.0/16:9090`, `:3100`, `:443`,
  `:6443` (443 et 6443 par cohérence avec AKS/GKE, utiles à 4K-102 pour ArgoCD).
- Mettre à jour le commentaire d'en-tête (liste des Connectors, mention 4K-101).

`terraform apply` écrase la policy de la console (`overwrite_existing_content = true`).
La règle Keycloak `tag:k8s:8080` (4K-15), marquée « à appliquer » dans l'en-tête, part
**dans le même apply** (**décision utilisateur**). Faire un `terraform plan` et vérifier
que le diff ne contient que les ajouts k3s et cette règle 8080 ; tout autre écart
(modification faite seulement dans la console) = s'arrêter et demander. Après l'apply,
retirer « à appliquer » de l'en-tête.

### 3. Stack monitoring

Installation par Helm, documentée dans une nouvelle section du README k3s (numérotation à la
suite des sections existantes), sur le modèle de la section 5 du README GKE :

```bash
helm upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace --version 91.8.2 \
  --values monitoring-values.yaml --kubeconfig cnp-k3s.yaml

helm upgrade --install loki grafana/loki-stack --namespace monitoring --version 2.10.3 \
  --values loki-values.yaml --kubeconfig cnp-k3s.yaml
```

Mêmes versions et noms de release qu'AKS/GKE → Services `kube-prometheus-stack-prometheus`
et `loki` dans `monitoring`, comme le suppose `infra/scripts/pin-clusterips.sh`.

**`infra/oracle/k3s/monitoring-values.yaml`** (nom aligné sur AKS/GKE plutôt que
`values-k3s.yaml` du ticket — *mon choix, cosmétique*) :

- `kube-state-metrics.metricLabelsAllowlist` identique à GKE.
- `kubeEtcd`, `kubeScheduler`, `kubeControllerManager`, `kubeProxy` : `enabled: false`
  (exigé par le ticket ; k3s embarque ces composants dans un seul binaire, métriques non
  exposées sur les ports standards).
- `coreDns` **reste activé** (k3s utilise CoreDNS, contrairement à GKE). Si sa cible est
  DOWN après install, la désactiver et le noter.
- `prometheus.service.clusterIP` figée (voir §4).
- Grafana in-cluster : **conservé** (défaut du chart, identique AKS/GKE ; le ticket n'en
  parle pas). Ne pas le désactiver dans ce ticket.

**`infra/oracle/k3s/loki-values.yaml`** (nouveau ; GKE passe tout en `--set`, ici un
fichier car il faut aussi figer la ClusterIP — *mon choix*) :

- `promtail.enabled: true`, `grafana.enabled: false`, `loki.isDefault: false`
  (obligatoire, cf. README GKE : sinon conflit de datasource par défaut).
- `loki.service.clusterIP` figée (voir §4).
- Promtail : le ticket exige le stage `cri` et le montage hostPath de `/var/log/pods` et
  `/var/log/containers`. Vérifier les défauts du sous-chart `promtail` de `loki-stack`
  2.10.3 ; ne surcharger que ce qui manque.
- Promtail, label `cnp.io/group-id` (**décision utilisateur**) : la config Promtail par
  défaut ne reprend pas les labels arbitraires des pods, et AKS/GKE n'ont *a priori* pas
  ce label dans Loki (le backend filtre les logs par `namespace`/`container` seulement).
  Sur k3s, ajouter une règle de relabel qui copie
  `__meta_kubernetes_pod_label_cnp_io_group_id` vers le label Loki `cnp_io_group_id`
  (nom : *mon choix*), en complément des relabels par défaut (ne pas les remplacer).
  Le faire aussi sur AKS/GKE est hors périmètre : le noter comme suivi dans le README.

**À vérifier à l'install** (exigences du ticket) :

- Images arm64 : tous les pods `monitoring` en `Running` (une image amd64 seule donne
  `exec format error`).
- metrics-server k3s : pas de conflit attendu (kube-prometheus-stack n'en installe pas) ;
  confirmer que `kubectl top nodes` fonctionne toujours.
- Prometheus → *Status > Targets* : aucune cible DOWN.
- Loki : une requête `{namespace="<ns d'une app CNP>"}` remonte des logs et le label
  `cnp_io_group_id` (ou nom équivalent après relabel) est présent, comme sur AKS. Si
  absent, comparer la config Promtail AKS et aligner.

### 4. ClusterIPs figées

Le ticket veut des ClusterIPs « connues et stables » pour 4K-102. Les figer dès
l'installation (plutôt que les relever après, cf. 4K-96 pour AKS) — *mon choix* :

- Prometheus : `10.43.200.90` (port 9090) ; Loki : `10.43.200.100` (port 3100).
- Avant install : `kubectl get svc -A` pour vérifier qu'elles sont libres ; en choisir
  d'autres dans `10.43.0.0/16` sinon, et les reporter partout (values, Grafana, README).
- Si la stack existe déjà sur le cluster (état non vérifiable au moment de la spec),
  relever ses IPs avec `infra/scripts/pin-clusterips.sh` et les figer telles quelles plutôt
  que d'en imposer de nouvelles.

### 5. Datasources Grafana central

Dans `infra/grafana/provisioning/datasources/cnp.yaml`, ajouter :

- `Prometheus cnp-k3s` — `type: prometheus`, `uid: prometheus-cnp-k3s`,
  `url: ${K3S_PROMETHEUS_URL}`, `editable: false`, mêmes `jsonData` que `Prometheus`.
- `Loki cnp-k3s` — `type: loki`, `uid: loki-cnp-k3s`, `url: ${K3S_LOKI_URL}`,
  `editable: false`, mêmes `jsonData` que `Loki`.
- Aucune des deux n'est `isDefault`. Les datasources `Prometheus` / `Loki` existantes ne
  changent pas.

Dans `docker-compose.yml`, service `grafana` : ajouter
`K3S_PROMETHEUS_URL=${K3S_PROMETHEUS_URL:-http://10.43.200.90:9090}` et
`K3S_LOKI_URL=${K3S_LOKI_URL:-http://10.43.200.100:3100}` (défauts = IPs figées).
Documenter les deux variables dans `.env.example`.

Déploiement sur `cnp-control` : redémarrer le service `grafana` pour recharger le
provisioning, puis *Connections > Data sources > Save & test* sur les deux datasources.

### 6. Documentation

- `infra/oracle/k3s/README.md` : section Tailscale (Connector + ACL + test `curl`) et
  section Monitoring (Helm, vérifications, IPs figées, datasources Grafana).
  Corriger le commentaire d'en-tête de `tailscale/operator-values.yaml` (« pas de
  Connector/subnet-router sur k3s ici » devient faux).
- `docs/adr/0020-observabilite-centralisee.md` : ajouter k3s comme source du Grafana central
  dans l'état actuel. Pas de nouvel ADR (pas de décision d'architecture nouvelle : on
  applique 0019/0020 comme AKS/GKE).
- `docs/adr/0019-tailscale-reseau-overlay.md` : seulement si une affirmation y devient
  fausse.

## Critères d'acceptation (adaptés du ticket)

Réseau
- [ ] `Connector` `k3s-subnet-router` `Ready`, device `tag:k8s` visible dans la console,
      route `10.43.0.0/16` approuvée (via autoApprovers).
- [ ] ACL appliquée, diff Terraform limité aux ajouts k3s + règle 8080 (4K-15).
- [ ] Depuis `cnp-control` : `curl http://<ClusterIP quelconque>:<port>` répond sans
      port-forward.

Monitoring
- [ ] `kube-prometheus-stack` et `loki-stack` déployés avec les values versionnées.
- [ ] Aucune cible Prometheus DOWN ; tous les pods `monitoring` `Running` sur arm64.
- [ ] Depuis `cnp-control` : `curl http://10.43.200.90:9090/-/ready` et
      `curl http://10.43.200.100:3100/ready` répondent.
- [ ] Logs des pods k3s dans Loki ; ceux des pods portant `cnp.io/group-id` ont le label
      Loki `cnp_io_group_id` (`{cnp_io_group_id="<id>"}` renvoie des lignes).

Grafana central
- [ ] Datasources `Prometheus cnp-k3s` et `Loki cnp-k3s` en état OK.
- [ ] Datasource par défaut et dashboards existants inchangés.

## Laissé à l'implémenteur

- Valeurs exactes des ClusterIPs si celles proposées sont prises.
- Surcharges Promtail nécessaires (selon les défauts du chart).
- Désactivation de `coreDns` si sa cible est DOWN.
- Numérotation et rédaction des sections README.

## Exécution

Les fichiers versionnés (connector, values, ACL, provisioning Grafana, compose, docs) sont
écrits dans la branche. Les actions sur l'infra live (`kubectl apply`, `helm`,
`terraform apply`, redémarrage Grafana sur `cnp-control`) sont faites par Lukas : le poste
de développement n'a pas d'accès au cluster k3s ni à `cnp-control`.
