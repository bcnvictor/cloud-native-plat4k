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
