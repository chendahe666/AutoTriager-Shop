#!/usr/bin/env bash
# Deploy the pinned official core + observability stack in the dedicated WSL distro.
# Source: https://github.com/open-telemetry/opentelemetry-demo/tree/3.1.0
set -Eeuo pipefail
umask 077
die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
[[ "$EUID" -eq 0 && "${WSL_DISTRO_NAME:-}" == AutoTriager-Shop ]] || die 'Run as root in the dedicated AutoTriager-Shop WSL distro.'
[[ "$(uname -r)" == *WSL2* ]] || die 'This script requires WSL2.'
source /etc/os-release
[[ "${ID:-}" == ubuntu && "${VERSION_ID:-}" == 24.04 && "$(dpkg --print-architecture)" == amd64 ]] || die 'Expected Ubuntu 24.04 amd64.'
[[ "$#" -eq 1 ]] || die 'Usage: deploy_official_shop.sh /mnt/d/项目/5588/AutoTriager-Shop/evaluation/private/runtime-TIMESTAMP'
for tool in git docker python3 realpath sha256sum; do
    command -v "$tool" >/dev/null || die "Missing prerequisite: $tool. Install it in AutoTriager-Shop before rerunning."
done
mountpoint -q /mnt/d || die 'The Windows D: drive is not mounted at /mnt/d.'
private_root=/mnt/d/项目/5588/AutoTriager-Shop/evaluation/private
log_root="$(realpath -m -- "$1")"
[[ "$log_root" == "$private_root"/runtime-* ]] || die 'Logs must be under the project evaluation/private/runtime-* path on D:.'
log_dir="$log_root/attempt-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -p -- "$log_dir"
printf 'Private deployment logs: %s\n' "$log_dir"
exec > >(tee -a "$log_dir/deploy.log") 2>&1

source_dir=/opt/autotriager/opentelemetry-demo
commit=dedc0178918e260823323b8d95005a8cb924b007
tag=3.1.0
project=autotriager-official
repository=https://github.com/open-telemetry/opentelemetry-demo.git
compose_ready=0
unset DOCKER_HOST DOCKER_CONTEXT DOCKER_TLS_VERIFY DOCKER_CERT_PATH
unset COMPOSE_FILE COMPOSE_PROJECT_NAME COMPOSE_PROFILES
export IMAGE_NAME=autotriager-local/astronomy-shop
export DEMO_VERSION=source-dedc0178918e IMAGE_VERSION=source-dedc0178918e
export COMPOSE_PARALLEL_LIMIT=2 COMPOSE_BAKE=false BUILDKIT_PROGRESS=plain
docker_local=(docker --host unix:///var/run/docker.sock)

record_runtime() {
    "${compose[@]}" ps --all --format json > "$log_dir/compose-ps.json" 2> "$log_dir/compose-ps.stderr" || return $?
    local ids=()
    "${compose[@]}" ps --all --quiet > "$log_dir/container-ids.txt" || return $?
    mapfile -t ids < "$log_dir/container-ids.txt" || return $?
    if ((${#ids[@]})); then
        "${docker_local[@]}" inspect "${ids[@]}" > "$log_dir/containers.json" || return $?
    else
        printf '[]\n' > "$log_dir/containers.json" || return $?
    fi
    python3 - "$log_dir" <<'PY' || return $?
import json, pathlib, sys
out = pathlib.Path(sys.argv[1])
containers = json.loads((out / "containers.json").read_text())
running = [{"container_id": c["Id"], "name": c["Name"],
            "configured_image": c["Config"]["Image"], "actual_image_id": c["Image"],
            "health": c["State"].get("Health", {}).get("Status", "not_defined")}
           for c in containers if c["State"].get("Running")]
(out / "running-container-image-map.json").write_text(json.dumps(running, indent=2) + "\n")
(out / "running-image-ids.txt").write_text("".join(i + "\n" for i in sorted({c["actual_image_id"] for c in running})))
PY
    local running_ids=()
    mapfile -t running_ids < "$log_dir/running-image-ids.txt" || return $?
    if ((${#running_ids[@]})); then
        "${docker_local[@]}" image inspect "${running_ids[@]}" > "$log_dir/running-images.json" || return $?
    else
        printf '[]\n' > "$log_dir/running-images.json" || return $?
    fi
    "${compose[@]}" logs --no-color --timestamps > "$log_dir/containers.log" 2>&1 || return $?
    return 0
}
on_exit() {
    local exit_code=$?
    trap - EXIT
    set +e
    if [[ "$compose_ready" -eq 1 ]]; then
        record_runtime
        printf 'Runtime evidence collection exit code: %s\n' "$?" > "$log_dir/runtime-evidence-status.txt"
    fi
    printf 'exit_code=%s\nhealth_validation=not_performed\nsource_commit=%s\nproject=%s\n' \
        "$exit_code" "$commit" "$project" > "$log_dir/outcome.txt"
    printf 'Deployment exited %s. Logs: %s. Application/capture health gates remain unchecked.\n' "$exit_code" "$log_dir"
    exit "$exit_code"
}
trap on_exit EXIT
trap 'printf "ERROR: stopped at line %s; preserve logs and correct the preceding error before rerunning.\n" "$LINENO" >&2' ERR

"${docker_local[@]}" version > "$log_dir/docker-version.txt"
"${docker_local[@]}" compose version > "$log_dir/compose-version.txt"
"${docker_local[@]}" info > "$log_dir/docker-info.txt"
if [[ ! -e "$source_dir" ]]; then
    mkdir -p /opt/autotriager
    git clone --branch "$tag" --single-branch --depth 1 "$repository" "$source_dir" 2>&1 | tee "$log_dir/clone.log"
fi
[[ -d "$source_dir/.git" ]] || die "$source_dir exists but is not the expected Git clone; it was preserved."
[[ "$(git -C "$source_dir" rev-parse --show-toplevel)" == "$source_dir" ]] || die 'Unexpected Git worktree root; source was preserved.'
origin="$(git -C "$source_dir" remote get-url origin)"
[[ "${origin%.git}" == "${repository%.git}" ]] || die 'Existing clone has an unexpected origin; source was preserved.'
git -C "$source_dir" status --porcelain=v1 --untracked-files=all > "$log_dir/source-status.txt"
git -C "$source_dir" show --no-patch --format=fuller HEAD > "$log_dir/source-commit.txt"
[[ "$(git -C "$source_dir" rev-parse HEAD)" == "$commit" ]] || die 'Existing clone is at the wrong commit; no checkout/reset was performed.'
[[ "$(git -C "$source_dir" rev-parse "refs/tags/$tag^{commit}")" == "$commit" ]] || die 'Tag does not resolve to the required commit.'
[[ ! -s "$log_dir/source-status.txt" ]] || die 'Existing source is dirty; changes were preserved. Review source-status.txt before rerunning.'

state_dir=/opt/autotriager/deployment-state/source-dedc0178918e
flag_dir=/opt/autotriager/runtime-flags/source-dedc0178918e
mkdir -p "$state_dir" "$(dirname "$flag_dir")"
if [[ ! -e "$flag_dir" ]]; then
    cp -a "$source_dir/src/flagd" "$flag_dir"
    sha256sum "$flag_dir/demo.flagd.json" > "$state_dir/flagd-initial.sha256"
fi
[[ -d "$flag_dir" && ! -L "$flag_dir" && -f "$flag_dir/demo.flagd.json" ]] || die 'Runtime flag copy is incomplete or symlinked; it was preserved. Review the runtime flags directory before rerunning.'
[[ ! "$flag_dir/demo.flagd.json" -ef "$source_dir/src/flagd/demo.flagd.json" ]] || die 'Runtime flags refer to the source file itself; source and runtime state must be separate.'
[[ -f "$state_dir/flagd-initial.sha256" ]] || die 'Existing runtime flag copy has no initial hash record; it was preserved. Establish its provenance before rerunning.'
cp -a "$state_dir/flagd-initial.sha256" "$log_dir/flagd-initial.sha256"
sha256sum "$source_dir/src/flagd/demo.flagd.json" "$flag_dir/demo.flagd.json" > "$log_dir/flagd-current.sha256"
stat -c '%a %U:%G %n' "$flag_dir" "$flag_dir/demo.flagd.json" > "$log_dir/flagd-permissions.txt"
git -C "$source_dir" status --porcelain=v1 --untracked-files=all > "$log_dir/source-status-before-config.txt"
[[ ! -s "$log_dir/source-status-before-config.txt" ]] || die 'Source changed while preparing runtime state; it was preserved.'

base_compose=("${docker_local[@]}" compose --ansi never --progress plain --parallel 2 \
    --project-name "$project" --project-directory "$source_dir" --env-file "$source_dir/.env")
"${base_compose[@]}" -f "$source_dir/compose.yaml" -f "$source_dir/compose.observability.yaml" \
    config --format json > "$log_dir/resolved-source-compose.json"
python3 - "$log_dir" "$project" "$IMAGE_NAME" "$DEMO_VERSION" "$flag_dir" "$source_dir" <<'PY'
import json, pathlib, sys
out = pathlib.Path(sys.argv[1])
project, prefix, version, flag_dir, source_dir = sys.argv[2:]
config = json.loads((out / "resolved-source-compose.json").read_text())
config["name"] = project
# The source-built Go binaries exceed the upstream 20 MiB limit on this host.
# Preserve this explicit environment adaptation separately from source identity.
memory_adaptations = []
for service in ("checkout", "product-catalog"):
    limits = config["services"][service]["deploy"]["resources"]["limits"]
    memory_adaptations.append({"service": service, "source_memory_bytes": limits["memory"],
                               "runtime_memory_bytes": "134217728"})
    limits["memory"] = "134217728"
(out / "memory-adaptations.json").write_text(json.dumps(memory_adaptations, indent=2) + "\n")
for service, target in (("flagd", "/etc/flagd"), ("flagd-ui", "/app/data")):
    matches = [v for v in config["services"][service].get("volumes", [])
               if v.get("type") == "bind" and v.get("target") == target
               and v.get("source") == str(pathlib.Path(source_dir) / "src/flagd")]
    if len(matches) != 1:
        raise SystemExit(f"Expected exactly one source flag bind for {service}:{target}")
    matches[0]["source"] = flag_dir
build, pull, plan = [], [], []
for service, spec in config["services"].items():
    spec.pop("container_name", None)
    for port in spec.get("ports", []):
        if not isinstance(port, dict):
            raise SystemExit(f"Unresolved port for {service}: {port!r}")
        port["host_ip"] = "127.0.0.1"
    is_build = bool(spec.get("build"))
    if is_build:
        expected = f"{prefix}:{version}-{service}"
        if spec.get("image") != expected:
            raise SystemExit(f"Unexpected source image for {service}: {spec.get('image')}")
        # Avoid consulting the registry for a cache image under our local-only prefix.
        spec["build"].pop("cache_from", None)
    (build if is_build else pull).append(service)
    plan.append({"service": service, "image": spec["image"], "operation": "build" if is_build else "pull"})
for kind in ("networks", "volumes"):
    for name, spec in config.get(kind, {}).items():
        if spec.get("external"):
            raise SystemExit(f"External {kind} are not allowed: {name}")
        spec["name"] = f"{project}-{name}"
if len(build) != 18 or len(pull) != 7:
    raise SystemExit(f"Source service plan changed: {len(build)} build, {len(pull)} pull; expected 18 and 7")
(out / "deployment-compose.json").write_text(json.dumps(config, indent=2) + "\n")
(out / "image-plan.json").write_text(json.dumps(plan, indent=2) + "\n")
for filename, values in (("build-services.txt", build), ("pull-services.txt", pull),
                         ("all-image-references.txt", sorted({p["image"] for p in plan})),
                         ("pull-image-references.txt", sorted({p["image"] for p in plan if p["operation"] == "pull"}))):
    (out / filename).write_text("".join(v + "\n" for v in values))
(out / "adaptations.txt").write_text(
    "Derived from pinned core + observability overlays. Removed fixed container_name values; "
    "scoped network/volume names to autotriager-official; bound published ports to 127.0.0.1; "
    "removed upstream build cache_from entries under the local image prefix; remapped flagd /etc/flagd "
    "and flagd-ui /app/data to a persistent state-owned flag copy. Existing flag interventions are "
    "preserved on retries; the initial copy hash and current hashes are recorded. Raised checkout and "
    "product-catalog memory limits from 20 MiB to 128 MiB after verified page-reclaim thrashing on this "
    "host; details are recorded separately. Source files unchanged.\n")
(out / "planned-counts.json").write_text(json.dumps({"build_services": len(build), "pull_services": len(pull),
                                                    "total_services": len(plan), "runtime_health": "not_checked"}, indent=2) + "\n")
PY
sha256sum "$log_dir/resolved-source-compose.json" "$log_dir/deployment-compose.json" > "$log_dir/config-sha256.txt"
compose=("${base_compose[@]}" -f "$log_dir/deployment-compose.json")
"${compose[@]}" config --quiet
compose_ready=1
mapfile -t pull_services < "$log_dir/pull-services.txt"
mapfile -t build_services < "$log_dir/build-services.txt"
"${compose[@]}" pull "${pull_services[@]}" 2>&1 | tee "$log_dir/pull-seven-services.log"
mapfile -t pull_images < "$log_dir/pull-image-references.txt"
"${docker_local[@]}" image inspect "${pull_images[@]}" > "$log_dir/pulled-images.json"
printf 'pull_services_completed=7\n' > "$log_dir/pull-outcome.txt"

build_flags=(--pull)
if [[ ! -e "$state_dir/first-build-started" ]]; then
    build_flags+=(--no-cache)
    printf '%s\n' "$log_dir" > "$state_dir/first-build-started"
fi
printf '%s\n' "${build_flags[*]}" > "$log_dir/build-flags.txt"
"${compose[@]}" build "${build_flags[@]}" "${build_services[@]}" 2>&1 | tee "$log_dir/build-eighteen-services.log"
printf 'build_services_completed=18\n' > "$log_dir/build-outcome.txt"
mapfile -t all_images < "$log_dir/all-image-references.txt"
"${docker_local[@]}" image inspect "${all_images[@]}" > "$log_dir/prepared-images.json"
"${compose[@]}" up --detach --no-build --pull never 2>&1 | tee "$log_dir/compose-up.log"
git -C "$source_dir" status --porcelain=v1 --untracked-files=all > "$log_dir/source-status-after.txt"
[[ ! -s "$log_dir/source-status-after.txt" ]] || die 'Source changed during deployment; inspect source-status-after.txt.'
printf 'Compose startup completed. Application and capture health checks are still required.\n'
