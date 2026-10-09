variable "project_id" {
  description = "ID du projet GCP (pas le nom affiché)"
  type        = string
}

variable "region" {
  description = "Région GCP"
  type        = string
  default     = "europe-west1"
}

variable "zone" {
  description = "Zone GCP du cluster (zonal = management fee couvert par le free tier)"
  type        = string
  default     = "europe-west1-b"
}

variable "cluster_name" {
  description = "Nom du cluster GKE (et de la ClusterConnection CNP)"
  type        = string
  default     = "cnp-gke"
}

variable "node_machine_type" {
  description = "Type de machine des nodes (e2-standard-2 = 2 vCPU, 8 GB RAM ; e2-medium (4 GB) ne suffit pas à la stack monitoring)"
  type        = string
  default     = "e2-standard-2"
}

variable "node_count" {
  description = "Nombre de nodes initial au provisioning"
  type        = number
  default     = 2
}

variable "node_min_count" {
  description = "Nombre minimum de nodes (autoscaler)"
  type        = number
  default     = 2
}

variable "node_max_count" {
  description = "Nombre maximum de nodes (autoscaler) — le quota CPU d'un compte d'essai est limité"
  type        = number
  default     = 3
}

variable "authorized_networks" {
  description = "CIDR autorisés à joindre l'API server. Vide = API publique (comme AKS)"
  type = list(object({
    name = string
    cidr = string
  }))
  default = []
}
