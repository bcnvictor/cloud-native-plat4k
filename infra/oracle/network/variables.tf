variable "oci_profile" {
  description = "Profil de ~/.oci/config (clé d'API du compte qui possède la VM k3s)"
  type        = string
  default     = "DEFAULT"
}

variable "region" {
  description = "Région OCI de la VM k3s (ex. eu-frankfurt-1) : voir la console, en haut à droite"
  type        = string
}

variable "compartment_id" {
  description = "OCID du compartiment de la security list"
  type        = string
}

variable "vcn_id" {
  description = "OCID du VCN de la VM k3s"
  type        = string
}

variable "security_list_id" {
  description = "OCID de la security list du subnet de la VM k3s (adoptée par import)"
  type        = string
}

variable "security_list_display_name" {
  description = "Nom affiché actuel de la security list (le reprendre tel quel pour ne pas le renommer)"
  type        = string
}

variable "vcn_cidr" {
  description = "CIDR du VCN (règle ICMP par défaut d'OCI)"
  type        = string
  default     = "10.0.0.0/16"
}

variable "k3s_api_source_cidr" {
  description = "Source de la règle 6443 ouverte aux opérateurs (aujourd'hui 0.0.0.0/0)"
  type        = string
}

variable "control_public_ip" {
  description = "IP publique de la VM cnp-control (backend CNP), autorisée sur 6443 en /32"
  type        = string
  default     = "130.61.112.206"
}

variable "vault_api_source_cidr" {
  description = "Source autorisée sur 8201 (API Vault de cnp-control) : aujourd'hui 0.0.0.0/0"
  type        = string
  default     = "0.0.0.0/0"
}
