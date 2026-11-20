variable "kubeconfig_path" {
  description = "Kubeconfig admin de cnp-k3s (récupéré par fetch-kubeconfig.sh, jamais versionné)"
  type        = string
  default     = "~/.kube/config-cnp-k3s"
}

variable "kube_context" {
  description = "Contexte explicite du cluster dans ce kubeconfig"
  type        = string
  default     = "cnp-k3s"
}

variable "ingress_nginx_chart_version" {
  description = "Version du chart ingress-nginx (4.15.1 = contrôleur v1.15.1 ; < v1.11.5 est vulnérable à CVE-2025-1974)"
  type        = string
  default     = "4.15.1"
}

variable "cert_manager_chart_version" {
  description = "Version du chart jetstack/cert-manager (CRDs installées par le chart : crds.enabled)"
  type        = string
  default     = "v1.21.3"
}

variable "cluster_name" {
  description = "Nom de la ClusterConnection CNP ; sert de txtOwnerId à external-dns"
  type        = string
  default     = "cnp-k3s"
}

variable "public_ip" {
  description = "IP publique de la VM OCI (NATée vers le nœud) publiée dans le status des Ingress, cible des enregistrements DNS external-dns"
  type        = string
  default     = "138.2.159.23"
}

variable "external_dns_chart_version" {
  description = "Version du chart kubernetes-sigs/external-dns (1.23.0 = external-dns v0.23.0)"
  type        = string
  default     = "1.23.0"
}

variable "letsencrypt_email" {
  description = "E-mail du compte ACME Let's Encrypt des ClusterIssuers (avis d'expiration/incidents)"
  type        = string
  default     = "contact@cloud-native-plat4k.me"
}
