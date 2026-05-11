# Kubeconfig complet pour kubectl et le backend FastAPI
# ATTENTION : contient des credentials - ne jamais commiter en clair
output "kubeconfig" {
  description = "Kubeconfig pour accéder au cluster AKS"
  value       = azurerm_kubernetes_cluster.cnp.kube_config_raw
  sensitive   = true
}

output "cluster_name" {
  description = "Nom du cluster AKS"
  value       = azurerm_kubernetes_cluster.cnp.name
}

output "resource_group_name" {
  description = "Nom du resource group"
  value       = azurerm_resource_group.cnp.name
}

output "cluster_endpoint" {
  description = "Endpoint de l'API server Kubernetes"
  value       = azurerm_kubernetes_cluster.cnp.kube_config[0].host
  sensitive   = true
}
