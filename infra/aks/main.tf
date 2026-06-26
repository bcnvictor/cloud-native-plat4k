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

  # Identité managée : Azure gère les credentials pour AKS automatiquement
  # Pas de service principal a rotation manuelle
  identity {
    type = "SystemAssigned"
  }

  # OIDC Issuer must remain enabled as it cannot be disabled once enabled on Azure AKS
  oidc_issuer_enabled = true

  # Réseau : kubenet est suffisant pour un cluster de dev/démo
  # Azure CNI serait nécessaire pour des intégrations réseau Azure avancées
  network_profile {
    network_plugin = "kubenet"
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
  version          = "4.10.1"
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
# Azure DNS zone — cloud-native-plat4k.me
# ---------------------------------------------------------------------------

resource "azurerm_dns_zone" "cnp" {
  name                = "cloud-native-plat4k.me"
  resource_group_name = azurerm_resource_group.cnp.name
}

# Wildcard A record : *.cloud-native-plat4k.me → IP nginx LB
resource "azurerm_dns_a_record" "wildcard" {
  name                = "*"
  zone_name           = azurerm_dns_zone.cnp.name
  resource_group_name = azurerm_resource_group.cnp.name
  ttl                 = 300
  records             = [data.kubernetes_service.ingress_nginx.status[0].load_balancer[0].ingress[0].ip]
}

# Apex A record (cloud-native-plat4k.me direct)
resource "azurerm_dns_a_record" "apex" {
  name                = "@"
  zone_name           = azurerm_dns_zone.cnp.name
  resource_group_name = azurerm_resource_group.cnp.name
  ttl                 = 300
  records             = [data.kubernetes_service.ingress_nginx.status[0].load_balancer[0].ingress[0].ip]
}
