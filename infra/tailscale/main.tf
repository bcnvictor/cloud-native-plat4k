terraform {
  required_providers {
    tailscale = {
      source  = "tailscale/tailscale"
      version = "~> 0.17"
    }
  }
  required_version = ">= 1.6"
}

# Provider auth : TAILSCALE_API_KEY ou TAILSCALE_OAUTH_CLIENT_ID + TAILSCALE_OAUTH_CLIENT_SECRET
# https://registry.terraform.io/providers/tailscale/tailscale/latest/docs
provider "tailscale" {
  tailnet = var.tailnet
}

# ---------------------------------------------------------------------------
# ACL policy
# ---------------------------------------------------------------------------
# autoApprovers évite de devoir approuver manuellement chaque route annoncée
# par les Connectors (AKS : 10.0.0.0/16, GKE : 34.118.224.0/20) dans l'admin console.
#
# Ce fichier reflète la policy en place dans la console (corrections ESO 4K-105,
# cf. infra/eso/README.md) + GKE (4K-244). overwrite_existing_content = true :
# toute modification faite uniquement dans la console est écrasée au prochain apply.

resource "tailscale_acl" "cnp" {
  overwrite_existing_content = true
  acl = jsonencode({
    tagOwners = {
      # tag:k8s propriétaire de lui-même : l'opérateur (OAuth client) délègue le tag
      # aux pods-proxy egress qu'il crée (ESO -> Vault, ADR-0024)
      "tag:k8s"          = ["autogroup:admin", "tag:k8s"]
      "tag:k8s-operator" = ["autogroup:admin"]
      "tag:cnp-control"  = ["autogroup:admin"]
    }

    autoApprovers = {
      routes = {
        "10.0.0.0/16"     = ["tag:k8s"] # Service CIDR AKS
        "34.118.224.0/20" = ["tag:k8s"] # Service CIDR GKE
      }
    }

    acls = [
      # cnp-control → AKS ClusterIPs via subnet router (10.0.0.0/16)
      # Sans cette règle CIDR, Tailscale ne distribue pas la route subnet à cnp-control.
      {
        action = "accept"
        src    = ["tag:cnp-control"]
        dst = [
          "10.0.0.0/16:9090", # Prometheus ClusterIP
          "10.0.0.0/16:3100", # Loki ClusterIP
          "10.0.0.0/16:443",  # ArgoCD HTTPS
          "10.0.0.0/16:6443", # Kubernetes API server
        ]
      },
      # cnp-control → GKE ClusterIPs via subnet router (34.118.224.0/20)
      {
        action = "accept"
        src    = ["tag:cnp-control"]
        dst = [
          "34.118.224.0/20:9090", # Prometheus ClusterIP
          "34.118.224.0/20:3100", # Loki ClusterIP
          "34.118.224.0/20:443",  # ArgoCD HTTPS
          "34.118.224.0/20:6443", # Kubernetes API server
        ]
      },
      # cnp-control → nodes Tailscale AKS directement (subnet router + operator)
      {
        action = "accept"
        src    = ["tag:cnp-control"]
        dst = [
          "tag:k8s:9090",
          "tag:k8s:3100",
          "tag:k8s:443",
          "tag:k8s:6443",
        ]
      },
      # Clusters → cnp-control : webhook ArgoCD → backend CNP, et ESO → Vault (8200)
      {
        action = "accept"
        src    = ["tag:k8s"]
        dst    = ["tag:cnp-control:443", "tag:cnp-control:8000", "tag:cnp-control:8200"]
      },
    ]
  })
}

# ---------------------------------------------------------------------------
# Auth key pour enrôler cnp-control
# ---------------------------------------------------------------------------
# Utilisée une seule fois lors du premier `tailscale up` sur la VM Oracle.
# Après enrôlement, la clé peut être révoquée — le device reste actif.

resource "tailscale_tailnet_key" "cnp_control" {
  reusable      = false
  ephemeral     = false
  preauthorized = true
  expiry        = 3600 # 1h : suffisant pour l'enrôlement, révoquée ensuite
  tags          = ["tag:cnp-control"]

  description = "cnp-control enrollment key"
}
