# Valeurs par défaut suffisantes pour le MVP
# Modifier node_count / node_max_count si besoin de plus de capacité

location            = "West Europe"
resource_group_name = "cnp-rg"
cluster_name        = "cnp-aks"
kubernetes_version  = "1.30"
node_vm_size        = "Standard_B2s"
node_count          = 2
node_min_count      = 2
node_max_count      = 4
