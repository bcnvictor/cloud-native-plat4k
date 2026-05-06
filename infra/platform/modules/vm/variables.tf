variable "project_name" { type = string }
variable "environment" { type = string }
variable "resource_group_name" { type = string }
variable "location" { type = string }
variable "subnet_id" { type = string }
variable "nsg_id" { type = string }
variable "vm_size" { type = string }
variable "tags" { type = map(string) }
