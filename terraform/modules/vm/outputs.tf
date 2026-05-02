output "public_ip" {
  value = azurerm_public_ip.pip.ip_address
}
output "fqdn" {
  value = azurerm_public_ip.pip.fqdn
}
output "ssh_private_key_path" {
  value = local_file.private_key.filename
}
