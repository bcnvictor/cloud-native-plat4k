variable "project_name" {
  type        = string
  description = "The name of the project, used for tagging and naming resources."
  default     = "cnp-platform"
}

variable "environment" {
  type        = string
  description = "The environment (dev, prod)."
  default     = "dev"
}

variable "region" {
  type        = string
  description = "Azure region for deployment."
  default     = "francecentral"
}

variable "admin_ip" {
  type        = string
  description = "Public IP allowed to access the VM via SSH."
}

variable "vm_size" {
  type        = string
  description = "Size of the Azure VM."
  default     = "Standard_B2s"
}
