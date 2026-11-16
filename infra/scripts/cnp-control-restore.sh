#!/usr/bin/env bash
# Restauration d'une sauvegarde produite par cnp-control-backup.sh.
#
# Cible par défaut : le docker LOCAL. Une cible distante se donne explicitement
# avec --ssh, et cnp-control (la prod) exige en plus --yes-prod.
#
# Usage :
#   infra/scripts/cnp-control-restore.sh db    <cnp-db.dump>       --container NOM
#   infra/scripts/cnp-control-restore.sh vault <vault-data.tar.gz> --volume NOM
set -euo pipefail

usage() {
    cat <<'EOF'
Usage :
  cnp-control-restore.sh db    <cnp-db.dump>       --container NOM [options]
  cnp-control-restore.sh vault <vault-data.tar.gz> --volume NOM    [options]

db     Restaure le dump dans le Postgres du conteneur NOM (en cours d'exécution),
       base et utilisateur pris dans ses variables POSTGRES_DB / POSTGRES_USER.
       Une seule transaction. Refuse une base qui contient déjà des tables,
       sauf avec --force (les objets existants sont alors supprimés).
vault  Extrait l'archive dans le volume NOM (créé s'il n'existe pas). Refuse un
       volume monté par un conteneur en cours d'exécution, et un volume non
       vide sauf avec --force (il est alors vidé). Démarrez ensuite Vault sur ce
       volume : il sera initialisé et scellé, à desceller avec 3 clés sur 5.

Options :
  --ssh HOST    Exécute sur HOST via SSH au lieu du docker local.
  --yes-prod    Obligatoire si HOST désigne cnp-control (la prod).
  --force       Écrase une base ou un volume non vide.
  -h, --help    Affiche cette aide.

Si un fichier SHA256SUMS est présent à côté de l'archive, la somme est vérifiée
avant toute modification. Variable optionnelle : CNP_RESTORE_TAR_IMAGE (image
utilisée pour écrire dans le volume, défaut alpine:3.20).
EOF
}

log() { printf '==> %s\n' "$*" >&2; }
die() { printf 'ERREUR : %s\n' "$*" >&2; exit 1; }

[[ $# -ge 1 ]] || { usage >&2; exit 2; }
case $1 in
    -h | --help) usage; exit 0 ;;
    db | vault) kind=$1 ;;
    *) usage >&2; die "commande inconnue : $1 (db ou vault)" ;;
esac
shift
[[ $# -ge 1 && $1 != -* ]] || die "fichier de sauvegarde manquant"
archive=$1
shift

container=
volume=
ssh_host=
yes_prod=false
force=false
tar_image=${CNP_RESTORE_TAR_IMAGE:-alpine:3.20}
while [[ $# -gt 0 ]]; do
    case $1 in
        --container) [[ $# -ge 2 ]] || die "--container attend une valeur"; container=$2; shift ;;
        --volume) [[ $# -ge 2 ]] || die "--volume attend une valeur"; volume=$2; shift ;;
        --ssh) [[ $# -ge 2 ]] || die "--ssh attend une valeur"; ssh_host=$2; shift ;;
        --yes-prod) yes_prod=true ;;
        --force) force=true ;;
        -h | --help) usage; exit 0 ;;
        *) usage >&2; die "option inconnue : $1" ;;
    esac
    shift
done

[[ -f "$archive" && -s "$archive" ]] || die "fichier absent ou vide : $archive"
name_re='^[A-Za-z0-9][A-Za-z0-9_.-]*$'
[[ "$tar_image" =~ ^[A-Za-z0-9][A-Za-z0-9_.:/@-]*$ ]] || die "image invalide : $tar_image"
if [[ $kind == db ]]; then
    [[ -n "$container" ]] || die "--container est obligatoire pour db"
    [[ "$container" =~ $name_re ]] || die "nom de conteneur invalide : $container"
else
    [[ -n "$volume" ]] || die "--volume est obligatoire pour vault"
    [[ "$volume" =~ $name_re ]] || die "nom de volume invalide : $volume"
fi

if [[ -n "$ssh_host" ]]; then
    [[ "$ssh_host" =~ ^[A-Za-z0-9_][A-Za-z0-9_.@-]*$ ]] || die "hôte SSH invalide : $ssh_host"
    case $ssh_host in
        *cnp-control* | *130.61.112.206*)
            $yes_prod || die "$ssh_host désigne la prod : ajoutez --yes-prod si c'est vraiment voulu" ;;
    esac
    target=$ssh_host
else
    target="docker local"
fi

# Somme de contrôle, si la sauvegarde est restaurée depuis son dossier d'origine.
sums="$(dirname "$archive")/SHA256SUMS"
if [[ -f "$sums" ]]; then
    base=$(basename "$archive")
    expected=$(awk -v f="$base" '$2 == f || $2 == "*" f { print $1 }' "$sums")
    if [[ -n "$expected" ]]; then
        if [[ $(uname -s) == Darwin ]] || ! command -v sha256sum >/dev/null 2>&1; then
            actual=$(shasum -a 256 "$archive" | awk '{ print $1 }')
        else
            actual=$(sha256sum "$archive" | awk '{ print $1 }')
        fi
        [[ "$actual" == "$expected" ]] || die "somme SHA256 incorrecte pour $archive"
        log "SHA256 vérifié ($base)"
    fi
fi

ssh_ctl_dir=
cleanup() {
    if [[ -n "$ssh_ctl_dir" ]]; then
        ssh -o ControlPath="$ssh_ctl_dir/%C" -O exit "$ssh_host" >/dev/null 2>&1 || true
        rm -rf "$ssh_ctl_dir"
    fi
}
trap cleanup EXIT
[[ -z "$ssh_host" ]] || ssh_ctl_dir=$(mktemp -d /tmp/cnp-rst.XXXXXX)

# Exécute une commande shell (une seule chaîne) sur la cible ; stdin passe tel quel.
on_target() {
    if [[ -z "$ssh_host" ]]; then
        bash -c "$1"
    else
        ssh -o ControlMaster=auto -o ControlPath="$ssh_ctl_dir/%C" -o ControlPersist=120 \
            -o ServerAliveInterval=30 "$ssh_host" "$1"
    fi
}

# Requête SQL lue sur stdin, exécutée par psql dans le conteneur (variables du conteneur).
psql_in() {
    on_target "docker exec -i $container sh -c 'exec psql -X -q -tA -v ON_ERROR_STOP=1 -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\"'"
}

restore_db() {
    log "Cible : $target, conteneur Postgres : $container"
    [[ $(on_target "docker inspect --format '{{.State.Running}}' $container" 2>/dev/null) == true ]] \
        || die "conteneur $container absent ou arrêté"
    local tables clean_opts=""
    tables=$(echo "select count(*) from pg_tables where schemaname = 'public';" | psql_in) \
        || die "impossible d'interroger la base du conteneur $container"
    if [[ "$tables" != 0 ]]; then
        $force || die "la base contient déjà $tables tables : relancez avec --force pour l'écraser"
        log "--force : les $tables tables existantes seront remplacées"
        clean_opts="--clean --if-exists"
    fi
    log "pg_restore (une seule transaction)..."
    on_target "docker exec -i $container sh -c 'exec pg_restore -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" --no-owner --single-transaction $clean_opts'" \
        < "$archive" || die "pg_restore a échoué (transaction annulée)"
    tables=$(echo "select count(*) from pg_tables where schemaname = 'public';" | psql_in)
    local head
    head=$(echo "select version_num from alembic_version;" | psql_in) || head="(absent)"
    log "Base restaurée : $tables tables, alembic_version = $head"
}

restore_vault() {
    log "Cible : $target, volume Vault : $volume"
    local users
    users=$(on_target "docker ps --filter volume=$volume --format '{{.Names}}'")
    [[ -z "$users" ]] || die "volume $volume monté par un conteneur en cours d'exécution ($users) : arrêtez ce Vault-là d'abord"
    if on_target "docker volume inspect $volume" >/dev/null 2>&1; then
        local first
        first=$(on_target "docker run --rm --network none -v $volume:/data:ro --entrypoint sh $tar_image -c 'ls -A /data | head -n 1'")
        if [[ -n "$first" ]]; then
            $force || die "le volume $volume n'est pas vide : relancez avec --force pour le vider"
            log "--force : vidage du volume $volume"
            on_target "docker run --rm --network none -v $volume:/data --entrypoint sh $tar_image -c 'find /data -mindepth 1 -delete'"
        fi
    else
        on_target "docker volume create $volume" >/dev/null
        log "Volume $volume créé"
    fi
    # --numeric-owner : conserve les uid/gid d'origine (utilisateur vault du conteneur).
    log "Extraction de l'archive..."
    on_target "docker run --rm -i --network none -v $volume:/data --entrypoint tar $tar_image --numeric-owner -xzf - -C /data" \
        < "$archive" || die "extraction échouée"
    on_target "docker run --rm --network none -v $volume:/data:ro --entrypoint sh $tar_image -c 'test -d /data/core'" \
        || die "core/ absent après extraction : archive inattendue"
    log "Volume restauré. Démarrez Vault dessus (stockage file, chemin du volume), puis :"
    log "  vault status            -> Initialized true, Sealed true"
    log "  vault operator unseal   -> 3 fois, avec 3 des 5 clés de déscellement"
}

if [[ $kind == db ]]; then restore_db; else restore_vault; fi
