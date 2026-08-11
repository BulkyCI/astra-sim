# DCS cluster runners for heavy evaluations

One just-in-time (JIT) GitHub Actions runner per experiment, scheduled by
SLURM, alive only while the experiment runs. No root, no docker, no PAT on
the cluster, nothing from the system but glibc.

## How it works

Every paired comparison in the evaluation matrix runs on the cluster
(structural experiments stay GitHub-hosted); the reusable workflow runs two
jobs per comparison:

1. `provision` (GitHub-hosted, ~1 min) mints a single-job JIT runner config
   with a one-hour GitHub App installation token, then pipes it over SSH to
   the cluster. The SSH key is bound to a forced command
   (`accept-runner.sh`) that can only submit one SLURM runner job — a
   leaked key gets no shell. The runner is labeled with the run id, so
   concurrent experiments can never swap runners.
2. `Cluster comparison` waits for that runner, builds the ns-3 binary with
   the rootless conda toolchain (`-march=native`: compile node is run
   node), and runs the whole three-arm comparison as one job (self-hosted
   jobs may run 5 days).

Job scratch lives in the cluster's sanctioned network scratch — the newest
`/scratch/scratch-space/expires-<date>` directory, whose expiry always
exceeds the job walltime — never in quota'd NFS home, the small `/var/tmp`
partition, or RAM-billed tmpfs `/tmp` (each of which has caused a distinct
fleet failure; the sbatch script probes them only as fallbacks).

The JIT runner deregisters itself and exits when its one job ends —
completed, failed, or cancelled — which ends the SLURM job and returns the
allocation. A 30-minute idle guard in `runner-job.sbatch` covers the
cancelled-while-queued case; `#SBATCH --time` is the absolute backstop.
Write-scoped jobs (`archive`, ledger) stay on GitHub-hosted runners: the
cluster only ever holds a `contents: read` token.

`accept-runner.sh` fast-forwards the repository clone and submits the
repo's own `runner-job.sbatch`, so a push deploys cluster-side changes on
the next provision. `build.sh` likewise reconciles the conda toolchain
against `buildenv-packages.txt` at job start; only `accept-runner.sh`
itself still deploys through `setup.sh`.

## Cluster setup (once)

```sh
git clone --no-recurse-submodules <repo-url> ~/astra-sim && cd ~/astra-sim
bash ci/dcs/setup.sh          # toolchain + pinned runner into ~/astra-ci
```

Generate a dedicated key pair (`ssh-keygen -t ed25519 -f astra-ci -N ''`)
and add the public half to `~/.ssh/authorized_keys` exactly as `setup.sh`
prints — with the forced command and `restrict`.

## GitHub configuration (once)

First create an org-owned GitHub App (no webhook, Repository permissions →
Administration: Read and write) and install it on this repository only.

| Kind   | Name                  | Value |
|--------|-----------------------|-------|
| secret | `DCS_APP_PRIVATE_KEY` | The app's .pem private key, file contents verbatim. |
| secret | `DCS_SSH_KEY`         | Private half of the dedicated key pair. |
| var    | `DCS_APP_ID`          | The app's Client ID (or numeric App ID). |
| var    | `DCS_SSH_DEST`        | e.g. `jfang@comps0.cs.toronto.edu` |
| var    | `DCS_SSH_HOST_KEY`    | One line from `ssh-keyscan -t ed25519 <host>` (pins the host, defeats MITM on the jitconfig hand-off). |

## Routing

Nothing to configure per entry: `comparison: true` in
`.github/workflows/evaluation-matrix.json` is what routes an experiment to
the cluster. Aggregations and the ledger are unaffected: the cluster job
uploads the same `<artifact_name>-<run id>` bundle the hosted single-job
path produced before the pivot.

## Pilot

Route a single heavy entry (e.g. the CLR-step burst pair) to `dcs`, push,
and watch: the provision job logs the SLURM job id; `squeue` shows the
runner job; the evaluation appears in the Actions UI as
"<name> (cluster)". Cancel the Actions job mid-run and confirm the SLURM
job ends within a minute — that is the lifecycle contract working.

## Teardown

Remove the `authorized_keys` line, delete the two GitHub secrets, and
`rm -rf ~/astra-ci`. There are no services, cron entries, or standing
registrations to clean up; JIT runners deregister themselves.
