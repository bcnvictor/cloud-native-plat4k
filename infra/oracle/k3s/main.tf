terraform {
  required_providers {
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

# k3s is installed by hand on the Oracle VM (install-k3s.sh): Terraform does not
# own the VM or the cluster, only the platform add-ons deployed into it. Access
# goes through the admin kubeconfig fetched by fetch-kubeconfig.sh.
provider "kubernetes" {
  config_path    = pathexpand(var.kubeconfig_path)
  config_context = var.kube_context
}

provider "helm" {
  kubernetes {
    config_path    = pathexpand(var.kubeconfig_path)
    config_context = var.kube_context
  }
}

# ---------------------------------------------------------------------------
# nginx-ingress-controller
# ---------------------------------------------------------------------------

# Same controller and IngressClass ("nginx") as AKS: CNP writes
# ingress.className=nginx for every exposed app (backend/gitlab/client.py).
# type=LoadBalancer is served by k3s ServiceLB (klipper-lb, enabled: only
# traefik is disabled), which binds ports 80/443 on the node itself.
resource "helm_release" "ingress_nginx" {
  name             = "ingress-nginx"
  repository       = "https://kubernetes.github.io/ingress-nginx"
  chart            = "ingress-nginx"
  version          = var.ingress_nginx_chart_version
  namespace        = "ingress-nginx"
  create_namespace = true
  atomic           = true
  timeout          = 600

  set {
    name  = "controller.service.type"
    value = "LoadBalancer"
  }
}

data "kubernetes_service" "ingress_nginx" {
  metadata {
    name      = "ingress-nginx-controller"
    namespace = "ingress-nginx"
  }
  depends_on = [helm_release.ingress_nginx]
}
