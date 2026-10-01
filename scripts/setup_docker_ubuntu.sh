#!/usr/bin/env bash
# Root-only installer for the dedicated AutoTriager-Shop Ubuntu 24.04 WSL2 distro.
# Source: https://docs.docker.com/engine/install/ubuntu/ (official apt repository).
set -Eeuo pipefail
trap 'printf "ERROR: setup stopped at line %s; correct the preceding error and rerun.\n" "$LINENO" >&2' ERR

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
log() { printf '%s\n' "$*"; }

[[ "$EUID" -eq 0 ]] || die 'Run as root: wsl.exe -d AutoTriager-Shop -u root -- bash /path/to/setup_docker_ubuntu.sh'
[[ "${WSL_DISTRO_NAME:-}" == AutoTriager-Shop ]] || die 'This installer only supports the dedicated WSL distro named AutoTriager-Shop.'
[[ "$(uname -r)" == *WSL2* ]] || die 'AutoTriager-Shop must use WSL2. Check wsl.exe --list --verbose from Windows.'
[[ -r /etc/os-release ]] || die '/etc/os-release is missing.'
# shellcheck source=/dev/null
source /etc/os-release
[[ "${ID:-}" == ubuntu && "${VERSION_ID:-}" == 24.04 && "${VERSION_CODENAME:-}" == noble ]] || die 'Expected Ubuntu 24.04 (noble). No packages were changed.'
[[ "$(dpkg --print-architecture)" == amd64 ]] || die 'Expected amd64 Ubuntu. No packages were changed.'

require_systemd() {
    local state
    if [[ "$(cat /proc/1/comm)" != systemd ]] || ! command -v systemctl >/dev/null; then
        die 'systemd is not PID 1. Enable [boot] systemd=true in /etc/wsl.conf, run wsl.exe --terminate AutoTriager-Shop from Windows, reopen this distro, and rerun.'
    fi
    state="$(timeout 60s systemctl is-system-running --wait 2>/dev/null || true)"
    case "$state" in
        running) ;;
        degraded) log 'systemd is ready but has failed units; inspect them with systemctl --failed.' ;;
        *) die "systemd is not ready (state: ${state:-unavailable}). Check systemctl --failed and journalctl -b; restart only AutoTriager-Shop and rerun." ;;
    esac
}

# Check before apt: Docker's packages may start the service during installation.
require_systemd
conflicts=()
for package in docker.io docker-compose docker-compose-v2 docker-doc docker-buildx podman podman-docker containerd runc; do
    status="$(dpkg-query -W -f='${db:Status-Status}' "$package" 2>/dev/null || true)"
    if [[ "$status" == installed ]]; then
        conflicts+=("$package")
    fi
done
if ((${#conflicts[@]})); then
    die "Conflicting packages are installed: ${conflicts[*]}. This installer removes nothing. Review these packages in AutoTriager-Shop before rerunning."
fi

export DEBIAN_FRONTEND=noninteractive
log 'Installing official Docker apt prerequisites.'
apt-get -o APT::Update::Error-Mode=any update
apt-get install -y --no-remove ca-certificates curl
install -m 0755 -d /etc/apt/keyrings
key_tmp="$(mktemp)"
trap 'rm -f -- "$key_tmp"' EXIT
curl --fail --silent --show-error --location --retry 3 \
    https://download.docker.com/linux/ubuntu/gpg -o "$key_tmp"
grep -q '^-----BEGIN PGP PUBLIC KEY BLOCK-----' "$key_tmp" || die 'Docker signing key download is invalid; check network/proxy settings and rerun.'
install -m 0644 "$key_tmp" /etc/apt/keyrings/docker.asc
cat > /etc/apt/sources.list.d/docker.sources <<'EOF'
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: amd64
Signed-By: /etc/apt/keyrings/docker.asc
EOF

log 'Installing Docker Engine, Buildx, and Compose from the official repository.'
apt-get -o APT::Update::Error-Mode=any update
apt-get install -y --no-remove \
    docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
require_systemd
if ! systemctl enable --now docker; then
    die 'Docker service failed. Inspect systemctl status docker --no-pager and journalctl -u docker -n 80 --no-pager, then rerun.'
fi
systemctl is-active --quiet docker || die 'Docker is inactive; inspect journalctl -u docker -n 80 --no-pager.'

# Explicitly use the local engine, even if this shell has a remote Docker context.
unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS_VERIFY DOCKER_CERT_PATH
docker --host unix:///var/run/docker.sock version
docker --host unix:///var/run/docker.sock compose version
if ! docker --host unix:///var/run/docker.sock run --rm hello-world; then
    die 'hello-world failed. Check Docker service logs and Docker Hub connectivity, then rerun. Installed packages were retained.'
fi
log 'Docker Engine and Compose are ready; hello-world completed successfully.'
