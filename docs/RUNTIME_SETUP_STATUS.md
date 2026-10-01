# Official Shop runtime setup: October 1, 2026

This checkpoint records installation work on the local Windows host. It is
not an official-Shop experiment result.

## Completed and verified

- Installed Microsoft WSL **3.0.1.0** from its official x64 MSI. The installer
  returned exit code **0**; `wsl --version` reports kernel **6.18.40.1-1**.
- Verified the MSI against the SHA-256 published in the Microsoft release
  metadata and a valid **Microsoft Corporation** Authenticode signature.
- Downloaded Ubuntu **24.04.5** for WSL from Canonical's release server. The
  388,975,696-byte archive matches the published SHA-256.
- Verified that `VirtualMachinePlatform` and
  `Microsoft-Windows-Subsystem-Linux` are enabled. `WslService` is running.
- Created a new WSL configuration with an 8 GB memory limit, six processors,
  and a 2 GB swap file on D:. No existing WSL configuration was overwritten.
  The intended project distribution and container data will also reside on D:.

## Current runtime gate

The project distribution installation was attempted with `--from-file`,
`--location`, `--name AutoTriager-Shop`, `--no-launch`, and `--version 2`.
Registration stopped with:

```text
Wsl/Service/RegisterDistro/CreateVm/HCS/HCS_E_SERVICE_NOT_AVAILABLE
```

No distribution is registered. The Windows compute service `vmcompute` and
network service `hns` were not found; Windows still reports a pending reboot.
The host reports 15.7 GB RAM, 16 logical processors and a present hypervisor.
The next action is a user-controlled Windows restart, followed by another
service/readiness check. Firmware changes are not justified by the current
evidence alone. The setup did not restart Windows automatically.

Docker Engine, the official Shop containers, and official incident captures
are **not running or verified yet**. GitHub authorization is a separate
publication task and does not prevent local deployment.

## Resume sequence

1. After restart, inspect WSL status, compute/network services, and existing
   distributions before retrying registration. Reuse the verified archive;
   do not overwrite any existing distribution.
2. Register the project-specific Ubuntu distribution on D:, verify its Linux
   kernel and systemd, and install Docker Engine and Compose from Docker's
   official Ubuntu package repository.
3. Verify a Docker test container, then follow the pinned source build and
   image-identity procedure in [SIMULATION_PROTOCOL.md](SIMULATION_PROTOCOL.md).
   Docker Desktop is not required for this Engine-in-Ubuntu route.
4. Verify the storefront, feature flags, Jaeger and Prometheus, then capture
   actual normal/fault/recovery windows and run the application comparison.
   Update the report only from those observed runs.

## Package provenance

| Package | Verified SHA-256 |
| --- | --- |
| `wsl.3.0.1.0.x64.msi` | `28b1a0d013640a2ac95898ea705fa186e5b4ff767a1c1b49257161bc106599c6` |
| `ubuntu-24.04.5-wsl-amd64.wsl` | `bb415d824822c4b878125729af451a5d18fb13d1cf5cbed9a7393ad64ac6039e` |

Installer files, installation logs and local verification records are stored
outside this Git repository in the workspace's `.runtime-installers` folder.
They are neither diagnostic model inputs nor public experiment cases.

Sources: [Microsoft WSL release](https://github.com/microsoft/WSL/releases/tag/3.0.1),
[Microsoft installation guide](https://learn.microsoft.com/en-us/windows/wsl/install),
[Ubuntu release checksums](https://releases.ubuntu.com/noble/SHA256SUMS),
[Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/).
