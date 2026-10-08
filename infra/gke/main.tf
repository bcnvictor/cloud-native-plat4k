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
  ip_allocation_policy {}

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

    oauth_scopes = ["https://www.googleapis.com/auth/cloud-platform"]

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
