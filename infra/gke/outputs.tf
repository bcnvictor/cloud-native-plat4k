output "cluster_name" {
  description = "Nom du cluster GKE"
  value       = google_container_cluster.cnp.name
}

output "cluster_location" {
  description = "Zone du cluster (pour gcloud container clusters get-credentials --zone)"
  value       = google_container_cluster.cnp.location
}

output "cluster_endpoint" {
  description = "Endpoint de l'API server Kubernetes"
  value       = "https://${google_container_cluster.cnp.endpoint}"
  sensitive   = true
}

output "get_credentials_command" {
  description = "Commande pour configurer kubectl sur ce cluster"
  value       = "gcloud container clusters get-credentials ${google_container_cluster.cnp.name} --zone ${google_container_cluster.cnp.location} --project ${var.project_id}"
}

output "nginx_lb_ip" {
  description = "IP publique du LoadBalancer nginx-ingress"
  value       = data.kubernetes_service.ingress_nginx.status[0].load_balancer[0].ingress[0].ip
}
