# Valeurs par défaut suffisantes pour le MVP
# Modifier node_count / node_max_count si besoin de plus de capacité

# Subscription "Azure for Students" de Thibault (l'ancienne, "Azure 4 Student Vic",
# est désactivée depuis 2026-11). Quota régional swedencentral : 6 vCPU.
subscription_id     = "4d2b2cea-305c-4133-a97e-d0e9c36e46ad"
location            = "Sweden Central"
resource_group_name = "cnp-rg"
cluster_name        = "cnp-aks"
kubernetes_version  = "1.35"
node_vm_size        = "Standard_B2ls_v2"
node_count          = 2
node_min_count      = 2
# 3 x 2 vCPU = 6 = quota régional ; 4 nœuds dépasserait le quota
node_max_count = 3
