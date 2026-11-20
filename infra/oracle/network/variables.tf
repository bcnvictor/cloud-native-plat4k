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
  description = "Source autorisée sur 6443 : la valeur actuelle de la règle (0.0.0.0/0 ou l'IP du backend en /32)"
  type        = string
}
