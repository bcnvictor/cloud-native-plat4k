# ServiceLB publishes the node addresses: the private OCI address, not the public
# IP (138.2.159.23), which OCI NATs to it. DNS records target the public IP.
output "ingress_nginx_lb_addresses" {
  description = "Adresses publiées par ServiceLB pour le Service ingress-nginx-controller"
  value       = [for i in data.kubernetes_service.ingress_nginx.status[0].load_balancer[0].ingress : i.ip]
}
