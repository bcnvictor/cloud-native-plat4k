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

  # k3s API server, used by the CNP backend and operators (infra/oracle/k3s/README.md §2).
  ingress_security_rules {
    source      = var.k3s_api_source_cidr
    source_type = "CIDR_BLOCK"
    protocol    = "6"
    stateless   = false
    tcp_options {
      min = 6443
      max = 6443
    }
  }

  # HTTP and HTTPS for ingress-nginx (ServiceLB binds them on the node): public app
  # URLs and the cert-manager HTTP-01 challenges.
  dynamic "ingress_security_rules" {
    for_each = [80, 443]
    content {
      source      = "0.0.0.0/0"
      source_type = "CIDR_BLOCK"
      protocol    = "6"
      stateless   = false
      tcp_options {
        min = ingress_security_rules.value
        max = ingress_security_rules.value
      }
    }
  }

  lifecycle {
    # Destroying it would cut SSH and the k3s API.
    prevent_destroy = true
  }
}
