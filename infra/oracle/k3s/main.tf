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

# ---------------------------------------------------------------------------
# cert-manager (HTTPS for exposed apps)
# ---------------------------------------------------------------------------

# CNP writes a Certificate (apps/{cluster}/{app}/platform/{env}/certificate.yaml)
# for every exposed app; cert-manager obtains it from Let's Encrypt over HTTP-01
# through ingress-nginx and stores it in the {app}-tls Secret the app's Ingress
# references. CRDs are installed (and kept on uninstall) by the chart itself.
resource "helm_release" "cert_manager" {
  name             = "cert-manager"
  repository       = "https://charts.jetstack.io"
  chart            = "cert-manager"
  version          = var.cert_manager_chart_version
  namespace        = "cert-manager"
  create_namespace = true
  atomic           = true
  timeout          = 600

  set {
    name  = "crds.enabled"
    value = "true"
  }

  set {
    name  = "crds.keep"
    value = "true"
  }

  depends_on = [helm_release.ingress_nginx]
}

# ClusterIssuers letsencrypt-prod / letsencrypt-staging, shipped as a local chart
# (shared with infra/aks): the ClusterIssuer CRD does not exist at plan time, so
# kubernetes_manifest cannot be used. cert-manager's startupapicheck hook makes
# the release above wait for a working webhook before this one is installed.
resource "helm_release" "cluster_issuers" {
  name      = "cnp-cluster-issuers"
  chart     = "${path.module}/../../cert-manager/cluster-issuers"
  namespace = "cert-manager"
  atomic    = true
  timeout   = 300

  set {
    name  = "email"
    value = var.letsencrypt_email
  }

  depends_on = [helm_release.cert_manager]
}
