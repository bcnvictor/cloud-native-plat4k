terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.13"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.30"
    }
  }
  required_version = ">= 1.6"
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Token OAuth de l'utilisateur gcloud courant : sert uniquement à Terraform pour
# piloter les providers kubernetes/helm. Le backend CNP utilise un kubeconfig
# statique (ServiceAccount), cf. create-cnp-kubeconfig.sh.
data "google_client_config" "current" {}

provider "kubernetes" {
  host                   = "https://${google_container_cluster.cnp.endpoint}"
  token                  = data.google_client_config.current.access_token
  cluster_ca_certificate = base64decode(google_container_cluster.cnp.master_auth[0].cluster_ca_certificate)
}

provider "helm" {
  kubernetes {
    host                   = "https://${google_container_cluster.cnp.endpoint}"
    token                  = data.google_client_config.current.access_token
    cluster_ca_certificate = base64decode(google_container_cluster.cnp.master_auth[0].cluster_ca_certificate)
  }
}

# ---------------------------------------------------------------------------
# Compte de service des nodes (moindre privilège)
# ---------------------------------------------------------------------------
# Sans compte dédié, les nodes tournent avec le compte Compute Engine par défaut,
# Editor sur le projet : n'importe quel pod pourrait en récupérer un jeton via le
# serveur de métadonnées et prendre la main sur tout le projet GCP.

resource "google_service_account" "gke_nodes" {
  account_id   = "${var.cluster_name}-nodes"
  display_name = "Nodes GKE ${var.cluster_name}"
}

# Rôle prédéfini minimal pour un node GKE (écriture des logs et métriques).
# Pas de artifactregistry.reader : les images CNP viennent du registry GitLab
# (pull secret), pas d'Artifact Registry.
resource "google_project_iam_member" "gke_nodes" {
  project = var.project_id
  role    = "roles/container.defaultNodeServiceAccount"
  member  = "serviceAccount:${google_service_account.gke_nodes.email}"
}

# ---------------------------------------------------------------------------
# GKE Cluster (Standard, zonal)
# ---------------------------------------------------------------------------

resource "google_container_cluster" "cnp" {
  name = var.cluster_name
  # Cluster zonal : les frais de management d'un cluster zonal par compte de
  # facturation sont couverts par le free tier GKE (un cluster régional ne l'est pas)
  location = var.zone

  # Le node pool par défaut ne se configure pas finement : on le supprime et on
  # gère le nôtre (google_container_node_pool.system) comme sur AKS
  remove_default_node_pool = true
  initial_node_count       = 1

  # Mode Standard (pas d'Autopilot, implicite ici) : la stack CNP a besoin de NET_ADMIN
  # (subnet-router Tailscale) et de hostPath (node-exporter, promtail), refusés par Autopilot

  release_channel {
    channel = "REGULAR"
  }

  # VPC-native : requis par GKE pour les IP de pods/services routables
  networking_mode = "VPC_NATIVE"
  # Service CIDR fixé explicitement : il est codé en dur dans tailscale/connector.yaml
  # et dans les ACL de infra/tailscale/main.tf (route annoncée à cnp-control)
  ip_allocation_policy {
    services_ipv4_cidr_block = var.services_cidr
  }

  # Workload Identity : prérequis du mode GKE_METADATA des nodes (cf. node_config),
  # qui masque aux pods le compte de service du node
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  # Restreindre l'API server aux IP connues (ex. cnp-control). Vide = API publique,
  # comme AKS aujourd'hui (authorizedIpRanges: null)
  dynamic "master_authorized_networks_config" {
    for_each = length(var.authorized_networks) > 0 ? [1] : []
    content {
      dynamic "cidr_blocks" {
        for_each = var.authorized_networks
        content {
          cidr_block   = cidr_blocks.value.cidr
          display_name = cidr_blocks.value.name
        }
      }
    }
  }

  # Cluster de démo : autoriser terraform destroy
  deletion_protection = false

  resource_labels = {
    project     = "cnp"
    environment = "shared"
    managed_by  = "terraform"
  }
}

resource "google_container_node_pool" "system" {
  name     = "system"
  cluster  = google_container_cluster.cnp.id
  location = google_container_cluster.cnp.location

  initial_node_count = var.node_count

  # La taille courante est pilotée par l'autoscaler et par la mise en pause
  # (resize à 0, cf. README) : sans ça, une reprise recréerait tout le node pool
  lifecycle {
    ignore_changes = [initial_node_count]
  }

  autoscaling {
    min_node_count = var.node_min_count
    max_node_count = var.node_max_count
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  node_config {
    machine_type = var.node_machine_type

    # Disque suffisant pour les images Docker ; pd-standard pour ne pas consommer
    # le quota SSD (limité sur les comptes d'essai)
    disk_size_gb = 50
    disk_type    = "pd-standard"

    # Compte dédié au lieu du compte Compute Engine par défaut (Editor). Le scope
    # cloud-platform ne donne alors que les droits IAM de ce compte.
    # Changer service_account force la recréation du node pool.
    service_account = google_service_account.gke_nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]

    # Les pods n'atteignent plus le serveur de métadonnées du node (donc pas son jeton) ;
    # exception : les pods hostNetwork (node-exporter), à réserver aux composants plateforme
    workload_metadata_config {
      mode = "GKE_METADATA"
    }

    labels = {
      project = "cnp"
    }
  }
}

# ---------------------------------------------------------------------------
# nginx-ingress-controller
# ---------------------------------------------------------------------------

resource "helm_release" "ingress_nginx" {
  name             = "ingress-nginx"
  repository       = "https://kubernetes.github.io/ingress-nginx"
  chart            = "ingress-nginx"
  version          = "4.10.1"
  namespace        = "ingress-nginx"
  create_namespace = true

  # Service LoadBalancer : GKE provisionne un Network Load Balancer externe
  set {
    name  = "controller.service.type"
    value = "LoadBalancer"
  }

  depends_on = [google_container_node_pool.system]
}

# Lire l'IP publique assignée par GCP au LoadBalancer nginx
data "kubernetes_service" "ingress_nginx" {
  metadata {
    name      = "ingress-nginx-controller"
    namespace = "ingress-nginx"
  }
  depends_on = [helm_release.ingress_nginx]
}

# ---------------------------------------------------------------------------
# cert-manager (HTTPS pour les apps exposées)
# ---------------------------------------------------------------------------

# Identique à infra/aks : CNP écrit un Certificate
# (apps/{cluster}/{app}/platform/{env}/certificate.yaml) pour chaque app exposée ;
# cert-manager l'obtient de Let's Encrypt en HTTP-01 via ingress-nginx et le range
# dans le Secret {app}-tls référencé par l'Ingress de l'app. Les CRDs sont
# installées (et conservées à la désinstallation) par le chart.
resource "helm_release" "cert_manager" {
  name             = "cert-manager"
  repository       = "https://charts.jetstack.io"
  chart            = "cert-manager"
  version          = "v1.21.3"
  namespace        = "cert-manager"
  create_namespace = true

  set {
    name  = "crds.enabled"
    value = "true"
  }

  set {
    name  = "crds.keep"
    value = "true"
  }

  depends_on = [helm_release.ingress_nginx]
}

# ClusterIssuers letsencrypt-prod / letsencrypt-staging, chart local partagé avec
# infra/aks et infra/oracle/k3s : la CRD ClusterIssuer n'existe pas au plan,
# kubernetes_manifest est donc inutilisable. Le hook startupapicheck de
# cert-manager fait attendre la release ci-dessus que le webhook réponde.
resource "helm_release" "cluster_issuers" {
  name      = "cnp-cluster-issuers"
  chart     = "${path.module}/../cert-manager/cluster-issuers"
  namespace = "cert-manager"

  set {
    name  = "email"
    value = var.letsencrypt_email
  }

  depends_on = [helm_release.cert_manager]
}

# ---------------------------------------------------------------------------
# DNS public des apps exposées (external-dns, Cloudflare)
# ---------------------------------------------------------------------------
# Le wildcard `*.cloud-native-plat4k.me` pointe vers AKS : external-dns crée un A
# par host d'Ingress de ce cluster (<slug>, dev.<slug>) vers l'IP du LoadBalancer
# nginx, prioritaire sur le wildcard (docs/guides/operations.md §9).

# Token Cloudflare (Vault secret/platform/external-dns) -> Secret
# external-dns/cloudflare-api-token, via ESO et le ClusterSecretStore vault-backend
# (prérequis manuels : README §6, policy eso-reader à jour). Chart local partagé
# avec infra/aks et infra/oracle/k3s, comme cluster_issuers.
resource "helm_release" "external_dns_token" {
  name             = "cnp-external-dns-cloudflare-token"
  chart            = "${path.module}/../external-dns/cloudflare-token"
  namespace        = "external-dns"
  create_namespace = true

  depends_on = [google_container_node_pool.system]
}

# Valeurs communes aux trois clusters dans infra/external-dns/values.yaml ;
# txtOwnerId = nom du cluster, pour qu'aucune instance ne modifie les
# enregistrements d'une autre.
resource "helm_release" "external_dns" {
  name       = "external-dns"
  repository = "https://kubernetes-sigs.github.io/external-dns"
  chart      = "external-dns"
  version    = "1.23.0" # external-dns v0.23.0
  namespace  = "external-dns"

  values = [file("${path.module}/../external-dns/values.yaml")]

  set {
    name  = "txtOwnerId"
    value = var.cluster_name
  }

  # L'IP publiée dans le status des Ingress vient d'ingress-nginx
  depends_on = [helm_release.ingress_nginx, helm_release.external_dns_token]
}
