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
# par le Connector AKS dans l'admin console.

resource "tailscale_acl" "cnp" {
  overwrite_existing_content = true
  acl = jsonencode({
    tagOwners = {
      "tag:k8s"          = ["autogroup:admin"]
      "tag:k8s-operator" = ["autogroup:admin"]
      "tag:cnp-control"  = ["autogroup:admin"]
    }

    autoApprovers = {
      routes = {
        "10.0.0.0/16" = ["tag:k8s"]
      }
    }

    acls = [
      # cnp-control → AKS ClusterIPs via subnet router (10.0.0.0/16)
      # Sans cette règle CIDR, Tailscale ne distribue pas la route subnet à cnp-control.
      {
        action = "accept"
        src    = ["tag:cnp-control"]
        dst = [
          "10.0.0.0/16:9090",  # Prometheus ClusterIP
          "10.0.0.0/16:3100",  # Loki ClusterIP
          "10.0.0.0/16:443",   # ArgoCD HTTPS
          "10.0.0.0/16:6443",  # Kubernetes API server
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
      # AKS → cnp-control : webhook entrant ArgoCD → CNP backend
      {
        action = "accept"
        src    = ["tag:k8s"]
        dst    = ["tag:cnp-control:443", "tag:cnp-control:8000"]
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
  expiry        = 3600  # 1h : suffisant pour l'enrôlement, révoquée ensuite
  tags          = ["tag:cnp-control"]

  description = "cnp-control enrollment key"
}
