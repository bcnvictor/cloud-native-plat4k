terraform {
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "~> 9.14"
    }
  }
  required_version = ">= 1.6"
}

# Auth: an OCI API key of the account that owns the k3s VM, in ~/.oci/config
# (profile var.oci_profile). Nothing secret lives in this directory.
provider "oci" {
  config_file_profile = var.oci_profile
  region              = var.region
}

# The security list of the k3s VM's subnet already exists (created by hand with
# the VM). It is adopted, not recreated: Terraform then owns ALL its rules, so
# every rule that exists today must be declared below. On the first plan, any
# existing rule missing here shows as removed — add it before applying
# (README: "Premier apply").
#
# The subnet is shared: this list also filters the control VM cnp-control
# (backend, front, webhooks, Vault). A rule removed here can cut those too.
# Descriptions are kept as they were in the console, so the import plan is clean.
import {
  to = oci_core_security_list.k3s
  id = var.security_list_id
}

resource "oci_core_security_list" "k3s" {
  compartment_id = var.compartment_id
  vcn_id         = var.vcn_id
  display_name   = var.security_list_display_name

  # Default OCI egress: everything out.
  egress_security_rules {
    destination      = "0.0.0.0/0"
    destination_type = "CIDR_BLOCK"
    protocol         = "all"
    stateless        = false
  }

  # SSH (default OCI rule).
  ingress_security_rules {
    source      = "0.0.0.0/0"
    source_type = "CIDR_BLOCK"
    protocol    = "6"
    stateless   = false
    tcp_options {
      min = 22
      max = 22
    }
  }

  # ICMP "fragmentation needed" from anywhere (default OCI rule, Path MTU discovery).
  ingress_security_rules {
    source      = "0.0.0.0/0"
    source_type = "CIDR_BLOCK"
    protocol    = "1"
    stateless   = false
    icmp_options {
      type = 3
      code = 4
    }
  }

  # ICMP "destination unreachable" from inside the VCN (default OCI rule).
  ingress_security_rules {
    source      = var.vcn_cidr
    source_type = "CIDR_BLOCK"
    protocol    = "1"
    stateless   = false
    icmp_options {
      type = 3
    }
  }

  # Vault API on cnp-control, read by External Secrets on every cluster and by
  # the backend (docker-compose.override.yml).
  ingress_security_rules {
    description = "Vault Dev Port"
    source      = var.vault_api_source_cidr
    source_type = "CIDR_BLOCK"
    protocol    = "6"
    stateless   = false
    tcp_options {
      min = 8201
      max = 8201
    }
  }

  # k3s API server from the CNP backend on cnp-control (infra/oracle/k3s/README.md §2).
  ingress_security_rules {
    source      = "${var.control_public_ip}/32"
    source_type = "CIDR_BLOCK"
    protocol    = "6"
    stateless   = false
    tcp_options {
      min = 6443
      max = 6443
    }
  }

  # k3s API server from var.k3s_api_source_cidr (today 0.0.0.0/0, operators).
  ingress_security_rules {
    description = "attempt 1 k3s"
    source      = var.k3s_api_source_cidr
    source_type = "CIDR_BLOCK"
    protocol    = "6"
    stateless   = false
    tcp_options {
      min = 6443
      max = 6443
    }
  }

  # HTTP and HTTPS: nginx on cnp-control (front, webhooks) and ingress-nginx on
  # cnp-k3s (ServiceLB binds them on the node: public app URLs, HTTP-01 challenges).
  ingress_security_rules {
    description = "Ingress webhooks pour le front"
    source      = "0.0.0.0/0"
    source_type = "CIDR_BLOCK"
    protocol    = "6"
    stateless   = false
    tcp_options {
      min = 80
      max = 80
    }
  }

  ingress_security_rules {
    description = "ingress 443 pour les webhooks"
    source      = "0.0.0.0/0"
    source_type = "CIDR_BLOCK"
    protocol    = "6"
    stateless   = false
    tcp_options {
      min = 443
      max = 443
    }
  }

  lifecycle {
    # Destroying it would cut SSH, the k3s API, Vault and the CNP front on both VMs.
    prevent_destroy = true
    # Many tenancies apply tag defaults (Oracle-Tags.CreatedBy/CreatedOn) to every
    # resource: without this, the first plan after import would try to remove them.
    ignore_changes = [defined_tags, freeform_tags]
  }
}
