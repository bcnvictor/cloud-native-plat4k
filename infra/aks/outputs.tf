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

output "nginx_lb_ip" {
  description = "IP publique du LoadBalancer nginx-ingress"
  value       = data.kubernetes_service.ingress_nginx.status[0].load_balancer[0].ingress[0].ip
}

output "dns_nameservers" {
  description = "Nameservers Azure DNS à configurer chez le registrar pour cloud-native-plat4k.me"
  value       = azurerm_dns_zone.cnp.name_servers
}
