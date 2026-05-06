output "vm_public_ip" {
  description = "The public IP address of the CNP platform VM."
  value       = module.vm.public_ip
}

output "vm_fqdn" {
  description = "The FQDN of the CNP platform VM."
  value       = module.vm.fqdn
}

output "ssh_private_key_path" {
  description = "Path to the generated SSH private key."
  value       = module.vm.ssh_private_key_path
  sensitive   = true
}
