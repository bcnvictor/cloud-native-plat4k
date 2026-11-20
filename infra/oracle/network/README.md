# Réseau Oracle Cloud de la VM k3s (Terraform)

Gère la **security list OCI** du subnet de la VM `cnp-k3s` (138.2.159.23). C'est le pare-feu
réseau d'Oracle, en amont de la VM : une session SSH n'y a pas accès. Il ouvre aujourd'hui
22 (SSH) et 6443 (API k3s) ; cette racine y ajoute **80 et 443** pour ingress-nginx (URLs
publiques des apps, challenges HTTP-01 de cert-manager).

Racine séparée de `infra/oracle/k3s/` : autre provider, autres identifiants (clé d'API du
compte Oracle), impact limité. La VM et le VCN ne sont pas gérés ici. L'état reste local
et non versionné, comme pour les autres racines : la personne qui applique le garde.

## Prérequis : clé d'API OCI

À faire par la personne qui a la console Oracle :

1. Console OCI → profil (en haut à droite) → **My profile** → **API keys** → **Add API key**
   → *Generate API key pair* → télécharger la clé privée → **Add**.
2. Recopier le bloc de configuration affiché dans `~/.oci/config` et y mettre le chemin
   de la clé privée (`key_file=`), en `chmod 600`. Ne jamais versionner la clé.
3. Relever, dans la console, les valeurs de `terraform.tfvars.example` :
   - Networking → Virtual Cloud Networks → le VCN de la VM : OCID du VCN, son CIDR et son
     compartiment ;
   - Security Lists → la security list du subnet de la VM : son **OCID**, son **nom
     exact** et la source actuelle de la règle 6443.

## Premier apply (adoption de la security list existante)

La security list existe déjà : le bloc `import` de `main.tf` la fait adopter par
Terraform, qui gère ensuite **toutes** ses règles. Une règle présente dans la console mais
absente de `main.tf` serait supprimée. D'où la procédure :

```bash
cd infra/oracle/network
cp terraform.tfvars.example terraform.tfvars   # puis remplir
terraform init
terraform plan
```

Le plan attendu : `1 to import, 0 to add, 1 to change, 0 to destroy`, et dans le détail
de `oci_core_security_list.k3s`, **seulement deux règles d'entrée ajoutées** (TCP 80 et
TCP 443).

Si le plan montre une règle supprimée (`-`), ou un autre changement (nom, source de la
règle 6443…), **ne pas appliquer** : corriger `main.tf` ou `terraform.tfvars`. Pour voir
la configuration exacte de l'existant, générer-la dans un dossier à part :

```bash
mkdir /tmp/oci-gen && cd /tmp/oci-gen
cat > main.tf <<'EOF'
provider "oci" {
  config_file_profile = "DEFAULT"
  region              = "<region>"
}
import {
  to = oci_core_security_list.k3s
  id = "<OCID de la security list>"
}
EOF
terraform init && terraform plan -generate-config-out=generated.tf
```

`generated.tf` contient alors toutes les règles actuelles, à reporter dans `main.tf` (par
PR) avant de relancer le plan. Quand le plan est conforme :

```bash
terraform apply
```

## Vérification

Depuis n'importe quel poste :

```bash
nc -z -G 5 138.2.159.23 80 && nc -z -G 5 138.2.159.23 443   # les deux doivent réussir
curl -sI http://138.2.159.23/   # 404 d'ingress-nginx attendu (aucun Ingress sur l'IP nue)
```

Le pare-feu local de la VM (iptables) ne devrait pas bloquer : le trafic vers les ports
de ServiceLB passe par les règles NAT/FORWARD que k3s installe. Si les ports restent
fermés alors que la security list est ouverte, vérifier iptables en SSH sur la VM.

## Modifications ultérieures

Toute nouvelle règle passe par une PR sur `main.tf`, puis `terraform plan` et `apply`,
plus par la console : une modification faite à la main serait écrasée au prochain apply.
`prevent_destroy` empêche de supprimer la security list par erreur, ce qui couperait SSH
et l'API k3s.
