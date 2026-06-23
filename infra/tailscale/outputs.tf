output "cnp_control_auth_key" {
  description = "Auth key à passer à `tailscale up --authkey` sur cnp-control. Valide 1h."
  value       = tailscale_tailnet_key.cnp_control.key
  sensitive   = true
}
