variable "subscription_id" {
  description = "Subscription Azure qui héberge le cluster (null = subscription par défaut de la CLI az)"
  type        = string
  default     = null
}

variable "location" {
  description = "Région Azure où déployer les ressources"
  type        = string
  default     = "West Europe"
}

variable "resource_group_name" {
  description = "Nom du resource group Azure"
  type        = string
  default     = "cnp-rg"
}

variable "cluster_name" {
  description = "Nom du cluster AKS"
  type        = string
  default     = "cnp-aks"
}

variable "kubernetes_version" {
  description = "Version Kubernetes à utiliser sur AKS"
  type        = string
  default     = "1.30"
}

variable "node_vm_size" {
  description = "Taille des VMs du node pool (Standard_B2s = 2 vCPU, 4 GB RAM)"
  type        = string
  default     = "Standard_B2s"
}

variable "node_count" {
  description = "Nombre de nodes initial au provisioning"
  type        = number
  default     = 2
}

variable "node_min_count" {
  description = "Nombre minimum de nodes (autoscaler)"
  type        = number
  default     = 2
}

variable "node_max_count" {
  description = "Nombre maximum de nodes (autoscaler)"
  type        = number
  default     = 4
}

variable "letsencrypt_email" {
  description = "E-mail du compte ACME Let's Encrypt des ClusterIssuers (avis d'expiration/incidents)"
  type        = string
  default     = "contact@cloud-native-plat4k.me"
}
