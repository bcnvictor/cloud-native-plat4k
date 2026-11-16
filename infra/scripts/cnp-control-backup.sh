#!/usr/bin/env bash
# Sauvegarde de cnp-control vers le laptop : base Postgres CNP + volume Vault.
#
# Tourne depuis le laptop et passe par SSH. Rien n'est arrêté ni redémarré sur
# la VM : pg_dump tourne dans le conteneur db, et le volume Vault est lu en
# lecture seule par un conteneur jetable pendant que Vault reste descellé.
# Les deux flux arrivent directement sur le laptop, rien n'est écrit sur la VM.
#
# Usage : infra/scripts/cnp-control-backup.sh [--check] [--local] [options]
# Restauration : infra/scripts/cnp-control-restore.sh
# Doc : docs/guides/cnp-control-deployment.md, section « Sauvegarde / restauration »
set -euo pipefail

usage() {
    cat <<'EOF'
Usage : cnp-control-backup.sh [options]

Sauvegarde la base Postgres CNP (pg_dump -Fc) et le volume Vault (tar.gz) de
cnp-control vers le laptop, en flux via SSH, sans arrêter aucun service.

Options :
  --host HOST      Cible SSH (alias ~/.ssh/config ou user@ip).
                   Défaut : $CNP_CONTROL_SSH, sinon « cnp-control ».
  --local          Utilise le docker local au lieu de SSH (tests de bout en bout).
  --project NAME   Projet docker compose. Défaut : $CNP_COMPOSE_PROJECT,
                   sinon « cloud-native-plat4k ».
  --dest DIR       Dossier racine des sauvegardes. Défaut : $CNP_BACKUP_DIR,
                   sinon ~/cnp-backups.
  --check          Préflight seul : résout le conteneur db et le volume Vault,
                   puis s'arrête. N'exécute rien dans les conteneurs.
  -h, --help       Affiche cette aide.

Variables optionnelles :
  CNP_VAULT_VOLUME      Volume Vault. Défaut : <projet>_vault_data.
  CNP_BACKUP_TAR_IMAGE  Image utilisée pour lire le volume. Défaut : l'image
                        du conteneur db, déjà présente (jamais de pull).

Résultat : <dest>/<horodatage UTC>/{cnp-db.dump,vault-data.tar.gz,SHA256SUMS}
EOF
}

log() { printf '==> %s\n' "$*" >&2; }
die() { printf 'ERREUR : %s\n' "$*" >&2; exit 1; }

ssh_host=${CNP_CONTROL_SSH:-cnp-control}
project=${CNP_COMPOSE_PROJECT:-cloud-native-plat4k}
backup_root=${CNP_BACKUP_DIR:-$HOME/cnp-backups}
vault_volume=${CNP_VAULT_VOLUME:-}
tar_image=${CNP_BACKUP_TAR_IMAGE:-}
local_mode=false
check_only=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --host) [[ $# -ge 2 ]] || die "--host attend une valeur"; ssh_host=$2; shift ;;
        --local) local_mode=true ;;
        --project) [[ $# -ge 2 ]] || die "--project attend une valeur"; project=$2; shift ;;
        --dest) [[ $# -ge 2 ]] || die "--dest attend une valeur"; backup_root=$2; shift ;;
        --check) check_only=true ;;
        -h | --help) usage; exit 0 ;;
        *) usage >&2; die "option inconnue : $1" ;;
    esac
    shift
done

# Ces noms sont insérés dans des commandes shell distantes : on n'accepte que
# des caractères sans signification pour le shell.
name_re='^[A-Za-z0-9][A-Za-z0-9_.-]*$'
[[ "$project" =~ $name_re ]] || die "nom de projet invalide : $project"
vault_volume=${vault_volume:-${project}_vault_data}
[[ "$vault_volume" =~ $name_re ]] || die "nom de volume invalide : $vault_volume"
[[ -z "$tar_image" || "$tar_image" =~ ^[A-Za-z0-9][A-Za-z0-9_.:/@-]*$ ]] || die "image invalide : $tar_image"
if ! $local_mode; then
    [[ "$ssh_host" =~ ^[A-Za-z0-9_][A-Za-z0-9_.@-]*$ ]] || die "hôte SSH invalide : $ssh_host"
fi

if [[ $(uname -s) == Darwin ]] || ! command -v sha256sum >/dev/null 2>&1; then
    sha256() { shasum -a 256 "$@"; }
else
    sha256() { sha256sum "$@"; }
fi

ssh_ctl_dir=
work_dir=
done_ok=false
cleanup() {
    if [[ -n "$ssh_ctl_dir" ]]; then
        ssh -o ControlPath="$ssh_ctl_dir/%C" -O exit "$ssh_host" >/dev/null 2>&1 || true
        rm -rf "$ssh_ctl_dir"
    fi
    if ! $done_ok && [[ -n "$work_dir" && -d "$work_dir" ]]; then
        rm -rf "$work_dir"
        printf 'Sauvegarde incomplète supprimée : %s\n' "$work_dir" >&2
    fi
}
trap cleanup EXIT

# Une seule connexion SSH partagée par tous les appels : une seule
# authentification. Chemin court dans /tmp (limite de 104 caractères sur macOS).
if ! $local_mode; then
    ssh_ctl_dir=$(mktemp -d /tmp/cnp-bkp.XXXXXX)
fi

# Exécute une commande shell (une seule chaîne) sur la cible : la VM via SSH,
# ou le docker local avec --local. stdin et stdout passent tels quels.
on_target() {
    if $local_mode; then
        bash -c "$1"
    else
        ssh -o ControlMaster=auto -o ControlPath="$ssh_ctl_dir/%C" -o ControlPersist=120 \
            -o ServerAliveInterval=30 "$ssh_host" "$1"
    fi
}

if $local_mode; then target="docker local"; else target="$ssh_host"; fi

# --- Préflight (lecture seule) ---------------------------------------------
log "Cible : $target, projet compose : $project"
db_container=$(on_target "docker ps --filter label=com.docker.compose.project=$project --filter label=com.docker.compose.service=db --format '{{.Names}}'") \
    || die "impossible d'interroger docker sur $target"
case $db_container in
    "") die "aucun conteneur db en cours d'exécution pour le projet $project" ;;
    *$'\n'*) die "plusieurs conteneurs db trouvés : $(echo "$db_container" | tr '\n' ' ')" ;;
esac
[[ "$db_container" =~ $name_re ]] || die "nom de conteneur inattendu : $db_container"
log "Conteneur Postgres : $db_container"

on_target "docker volume inspect --format '{{.Name}}' $vault_volume" >/dev/null 2>&1 \
    || die "volume Vault introuvable : $vault_volume (voir CNP_VAULT_VOLUME)"
log "Volume Vault : $vault_volume"

if [[ -z "$tar_image" ]]; then
    tar_image=$(on_target "docker inspect --format '{{.Image}}' $db_container")
fi
[[ "$tar_image" =~ ^[A-Za-z0-9][A-Za-z0-9_.:/@-]*$ ]] || die "image inattendue : $tar_image"
log "Image de lecture du volume : $tar_image"

if $check_only; then
    log "Préflight OK (--check) : rien n'a été sauvegardé."
    exit 0
fi

# --- Destination -------------------------------------------------------------
umask 077
stamp=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$backup_root"
dest="$backup_root/$stamp"
[[ ! -e "$dest" ]] || die "la destination existe déjà : $dest"
# On écrit dans un dossier .partial renommé à la fin : un dossier horodaté
# présent dans $backup_root est toujours une sauvegarde complète et vérifiée.
work_dir="$backup_root/.$stamp.partial"
mkdir -m 700 "$work_dir"

# --- 1. Base CNP --------------------------------------------------------------
# pg_dump tourne dans le conteneur db avec ses propres variables d'environnement
# (développées dans le conteneur grâce aux quotes simples) : aucun secret ne
# transite par ce script. Socket local, pas de TTY (sortie binaire).
log "Dump de la base (pg_dump -Fc)..."
on_target "docker exec $db_container sh -c 'exec pg_dump -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Fc'" \
    > "$work_dir/cnp-db.dump" || die "pg_dump a échoué"
[[ -s "$work_dir/cnp-db.dump" ]] || die "dump vide"

# --- 2. Volume Vault ------------------------------------------------------------
# Conteneur jetable, volume monté en lecture seule, sans réseau, sans pull.
# Vault n'est ni arrêté ni redémarré : il se rescellerait. Stockage « file » :
# copie à chaud, cohérente tant qu'aucune écriture n'a lieu pendant les quelques
# secondes du tar (voir la doc).
log "Archive du volume Vault (lecture seule, Vault reste allumé)..."
on_target "docker run --rm --pull=never --network none -v $vault_volume:/data:ro --entrypoint tar $tar_image czf - -C /data ." \
    > "$work_dir/vault-data.tar.gz" || die "archive du volume Vault échouée"
[[ -s "$work_dir/vault-data.tar.gz" ]] || die "archive Vault vide"

# --- 3. Vérifications -------------------------------------------------------------
log "Vérification du dump (pg_restore --list dans le conteneur db, sans connexion à la base)..."
toc=$(on_target "docker exec -i $db_container pg_restore --list" < "$work_dir/cnp-db.dump") \
    || die "pg_restore --list ne relit pas le dump"
toc_entries=$(printf '%s\n' "$toc" | grep -c -v -e '^;' -e '^$' || true)
printf '%s\n' "$toc" | grep -q ' TABLE public alembic_version ' \
    || die "le dump ne contient pas la table alembic_version : est-ce bien la base CNP ?"
log "Dump lisible : $toc_entries entrées, table alembic_version présente"

log "Vérification de l'archive Vault (tar tzf)..."
listing=$(tar tzf "$work_dir/vault-data.tar.gz") || die "tar tzf ne relit pas l'archive Vault"
printf '%s\n' "$listing" | grep -q '^\./core/' \
    || die "l'archive ne contient pas core/ : est-ce bien le volume de stockage Vault ?"
log "Archive lisible : $(printf '%s\n' "$listing" | grep -c .) entrées"

(cd "$work_dir" && sha256 cnp-db.dump vault-data.tar.gz > SHA256SUMS && sha256 -c SHA256SUMS >/dev/null) \
    || die "contrôle SHA256 échoué"

mv "$work_dir" "$dest"
done_ok=true

log "Sauvegarde terminée : $dest"
(cd "$dest" && ls -l cnp-db.dump vault-data.tar.gz SHA256SUMS) >&2
cat >&2 <<EOF

Rappels :
  - Copiez ce dossier hors du laptop (stockage chiffré de l'équipe).
  - L'archive Vault est chiffrée par la barrière Vault : elle ne sert à rien
    sans 3 des 5 clés de déscellement, conservées séparément. Ne les stockez
    jamais à côté de la sauvegarde.
  - Non sauvegardés : .env de la VM, certificats Let's Encrypt, Grafana.
EOF
