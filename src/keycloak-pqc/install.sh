#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: ./install.sh [options]

Helpers for the Keycloak + Luna HSM PoC:
  --java-home <path>          Path to the JDK used by Keycloak
  --enable-luna-provider      Patch java.security with Luna provider entries
  --restore-java-security     Restore the backed up java.security
  --copy-spi <src> <dst>      Copy the Luna Keycloak SPI module into Keycloak modules
  --restart-compose           Restart the docker compose stack defined in docker-compose.yml
  -h, --help                  Show this message

Examples:
  sudo ./install.sh --java-home /opt/jdk-11 --enable-luna-provider
  ./install.sh --copy-spi /opt/luna-spi/com /opt/keycloak/modules
  ./install.sh --restart-compose
USAGE
}

JAVA_HOME=""
ENABLE_PROVIDER=false
RESTORE_PROVIDER=false
COPY_SPI=false
SPI_SRC=""
SPI_DST=""
RESTART_COMPOSE=false

ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    --java-home)
      JAVA_HOME="$2"; shift 2 ;;
    --enable-luna-provider)
      ENABLE_PROVIDER=true; shift ;;
    --restore-java-security)
      RESTORE_PROVIDER=true; shift ;;
    --copy-spi)
      COPY_SPI=true; SPI_SRC="$2"; SPI_DST="$3"; shift 3 ;;
    --restart-compose)
      RESTART_COMPOSE=true; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      ARGS+=("$1"); shift ;;
  esac
done

if [[ ${#ARGS[@]} -gt 0 ]]; then
  echo "Unknown arguments: ${ARGS[*]}" >&2
  usage
  exit 1
fi

backup_java_security() {
  local java_home="$1"
  local security_file="$java_home/conf/security/java.security"
  if [[ ! -f "$security_file" ]]; then
    echo "java.security not found at $security_file" >&2
    exit 1
  fi
  local backup_file="$security_file.bak"
  if [[ ! -f "$backup_file" ]]; then
    cp "$security_file" "$backup_file"
    echo "Backup created at $backup_file"
  else
    echo "Backup already exists at $backup_file"
  fi
}

restore_java_security() {
  local java_home="$1"
  local security_file="$java_home/conf/security/java.security"
  local backup_file="$security_file.bak"
  if [[ ! -f "$backup_file" ]]; then
    echo "No backup found at $backup_file" >&2
    exit 1
  fi
  cp "$backup_file" "$security_file"
  echo "java.security restored from backup"
}

ensure_luna_provider() {
  local java_home="$1"
  local security_file="$java_home/conf/security/java.security"
  backup_java_security "$java_home"
  if grep -q "com.safenetinc.luna.provider.LunaProvider" "$security_file"; then
    echo "Luna provider already present in java.security"
    return
  fi
  cat <<'PROVIDERS' >> "$security_file"

# Added by install.sh to enable the Luna Provider
security.provider.11=SunPKCS11
security.provider.12=com.safenetinc.luna.provider.LunaProvider
security.provider.13=SunRsaSign
PROVIDERS
  echo "Luna provider entries appended to $security_file"
}

copy_spi_module() {
  local src="$1"
  local dst="$2"
  if [[ ! -d "$src" ]]; then
    echo "SPI source directory $src does not exist" >&2
    exit 1
  fi
  mkdir -p "$dst"
  rsync -a "$src/" "$dst/"
  echo "Copied SPI module from $src to $dst"
}

restart_compose() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "docker command not found" >&2
    exit 1
  fi
  if ! command -v docker compose >/dev/null 2>&1; then
    echo "docker compose plugin not available" >&2
    exit 1
  fi
  docker compose -f "$(dirname "$0")/docker-compose.yml" down
  docker compose -f "$(dirname "$0")/docker-compose.yml" up -d
}

if $RESTORE_PROVIDER; then
  if [[ -z "$JAVA_HOME" ]]; then
    echo "--java-home is required when restoring java.security" >&2
    exit 1
  fi
  restore_java_security "$JAVA_HOME"
fi

if $ENABLE_PROVIDER; then
  if [[ -z "$JAVA_HOME" ]]; then
    echo "--java-home is required when enabling the Luna provider" >&2
    exit 1
  fi
  ensure_luna_provider "$JAVA_HOME"
fi

if $COPY_SPI; then
  copy_spi_module "$SPI_SRC" "$SPI_DST"
fi

if $RESTART_COMPOSE; then
  restart_compose
fi

if ! $ENABLE_PROVIDER && ! $RESTORE_PROVIDER && ! $COPY_SPI && ! $RESTART_COMPOSE; then
  usage
  exit 0
fi
