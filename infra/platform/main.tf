provider "azurerm" {
  features {}
}

locals {
  common_tags = {
    project    = var.project_name
    environment = var.environment
    managed_by = "terraform"
  }
}

resource "azurerm_resource_group" "rg" {
  name     = "${var.project_name}-${var.environment}-rg"
  location = var.region
  tags     = local.common_tags
}

module "network" {
  source              = "./modules/network"
  project_name        = var.project_name
  environment         = var.environment
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  admin_ip            = var.admin_ip
  tags                = local.common_tags
}

module "vm" {
  source              = "./modules/vm"
  project_name        = var.project_name
  environment         = var.environment
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  subnet_id           = module.network.subnet_id
  nsg_id              = module.network.nsg_id
  vm_size             = var.vm_size
  tags                = local.common_tags
}
