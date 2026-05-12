terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.100"
    }
  }
  required_version = ">= 1.6"
}

provider "azurerm" {
  features {}
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
