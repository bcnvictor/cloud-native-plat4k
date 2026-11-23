terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100"
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

provider "azurerm" {
  features {}
  # Subscription explicite : ne dépend pas de la subscription par défaut de la CLI `az`
  subscription_id = var.subscription_id
}

provider "kubernetes" {
  host                   = azurerm_kubernetes_cluster.cnp.kube_config[0].host
  client_certificate     = base64decode(azurerm_kubernetes_cluster.cnp.kube_config[0].client_certificate)
  client_key             = base64decode(azurerm_kubernetes_cluster.cnp.kube_config[0].client_key)
  cluster_ca_certificate = base64decode(azurerm_kubernetes_cluster.cnp.kube_config[0].cluster_ca_certificate)
}

provider "helm" {
  kubernetes {
    host                   = azurerm_kubernetes_cluster.cnp.kube_config[0].host
    client_certificate     = base64decode(azurerm_kubernetes_cluster.cnp.kube_config[0].client_certificate)
    client_key             = base64decode(azurerm_kubernetes_cluster.cnp.kube_config[0].client_key)
    cluster_ca_certificate = base64decode(azurerm_kubernetes_cluster.cnp.kube_config[0].cluster_ca_certificate)
  }
}

# ---------------------------------------------------------------------------
# Resource Group
# ---------------------------------------------------------------------------

resource "azurerm_resource_group" "cnp" {
  name     = var.resource_group_name
  location = var.location

  tags = {
    project     = "cnp"
    environment = "shared"
    managed_by  = "terraform"
  }
}

# ---------------------------------------------------------------------------
# AKS Cluster
# ---------------------------------------------------------------------------

resource "azurerm_kubernetes_cluster" "cnp" {
  name                = var.cluster_name
  location            = azurerm_resource_group.cnp.location
  resource_group_name = azurerm_resource_group.cnp.name
  dns_prefix          = var.cluster_name
  kubernetes_version  = var.kubernetes_version

  # Node pool système : fait tourner les composants Kubernetes internes
  default_node_pool {
    name                = "system"
    vm_size             = var.node_vm_size
    node_count          = var.node_count
    min_count           = var.node_min_count
    max_count           = var.node_max_count
    enable_auto_scaling = true

    # Disque OS suffisant pour les images Docker
    os_disk_size_gb = 50
  }

  # OIDC issuer : ne peut pas être désactivé une fois activé sur Azure
  oidc_issuer_enabled = true

  # Identité managée : Azure gère les credentials pour AKS automatiquement
  # Pas de service principal a rotation manuelle
  identity {
    type = "SystemAssigned"
  }

  # Réseau : kubenet est suffisant pour un cluster de dev/démo
  # Azure CNI serait nécessaire pour des intégrations réseau Azure avancées
  network_profile {
    network_plugin    = "kubenet"
    load_balancer_sku = "standard"
  }

  tags = {
    project     = "cnp"
    environment = "shared"
    managed_by  = "terraform"
  }
}

# ---------------------------------------------------------------------------
# nginx-ingress-controller
# ---------------------------------------------------------------------------

resource "helm_release" "ingress_nginx" {
  name             = "ingress-nginx"
  repository       = "https://kubernetes.github.io/ingress-nginx"
  chart            = "ingress-nginx"
  version          = "4.15.1" # >= 4.12.1 : CVE-2025-1974 (IngressNightmare), aligné sur k3s
  namespace        = "ingress-nginx"
  create_namespace = true

  set {
    name  = "controller.service.type"
    value = "LoadBalancer"
  }

  set {
    name  = "controller.service.annotations.service\\.beta\\.kubernetes\\.io/azure-load-balancer-health-probe-request-path"
    value = "/healthz"
  }

  depends_on = [azurerm_kubernetes_cluster.cnp]
}

# Lire l'IP publique assignée par Azure au LoadBalancer nginx
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

# CNP écrit un Certificate (apps/{cluster}/{app}/platform/{env}/certificate.yaml)
# pour chaque app exposée ; cert-manager l'obtient de Let's Encrypt en HTTP-01 via
# ingress-nginx et le range dans le Secret {app}-tls référencé par l'Ingress de
# l'app. Les CRDs sont installées (et conservées à la désinstallation) par le chart.
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

# ClusterIssuers letsencrypt-prod / letsencrypt-staging, livrés en chart local
# (partagé avec infra/oracle/k3s) : la CRD ClusterIssuer n'existe pas au plan,
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
# DNS
# ---------------------------------------------------------------------------
# La zone cloud-native-plat4k.me est servie par Cloudflare (NS *.ns.cloudflare.com,
# registrar Namecheap). Le wildcard A `*` (manuel) pointe vers l'ingress d'AKS,
# cluster par défaut : après un (re)provisioning, le mettre à jour avec
# `terraform output nginx_lb_ip`. Chaque cluster crée en plus, via external-dns,
# un A par host d'Ingress exposé (docs/guides/operations.md §9).
# (L'ancienne zone Azure DNS n'était pas déléguée et a été retirée.)

# Token Cloudflare (Vault secret/platform/external-dns) -> Secret
# external-dns/cloudflare-api-token, via ESO et le ClusterSecretStore vault-backend
# (prérequis manuels : infra/eso/README.md, policy eso-reader à jour). Chart local
# partagé par les trois clusters plutôt que kubernetes_manifest : même raison que
# cluster_issuers (le provider kubernetes dépend du cluster créé dans ce root, et
# kubernetes_manifest exige l'API et la CRD dès le plan).
resource "helm_release" "external_dns_token" {
  name             = "cnp-external-dns-cloudflare-token"
  chart            = "${path.module}/../external-dns/cloudflare-token"
  namespace        = "external-dns"
  create_namespace = true

  depends_on = [azurerm_kubernetes_cluster.cnp]
}

# external-dns (fournisseur Cloudflare, source Ingress). Valeurs communes aux trois
# clusters dans infra/external-dns/values.yaml ; txtOwnerId = nom du cluster, pour
# qu'aucune instance ne modifie les enregistrements d'une autre.
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
