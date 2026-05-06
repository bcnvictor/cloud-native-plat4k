terraform {
  backend "azurerm" {
    # This backend configuration should be passed via CLI args during init
    # terraform init -backend-config="resource_group_name=tfstate-rg" -backend-config="storage_account_name=tfstatestore" -backend-config="container_name=tfstate" -backend-config="key=cnp.tfstate"
  }
}
