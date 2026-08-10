# DCS cluster runners for heavy evaluations

One just-in-time (JIT) GitHub Actions runner per experiment, scheduled by
SLURM, alive only while the experiment runs. No root, no docker, no PAT on
the cluster, nothing from the system but glibc.

## How it works

For a matrix entry with `"runs_on": "dcs"`, the reusable workflow replaces
the hosted per-arm chain with two jobs:

1. `provision` (GitHub-hosted, ~1 min) mints a single-job JIT runner config
   with a repo-secret PAT, then pipes it over SSH to the cluster. The SSH
   key is bound to a forced command (`accept-runner.sh`) that can only
   submit one SLURM runner job — a leaked key gets no shell.
2. `evaluate_cluster` waits for that runner, builds the ns-3 binary with the
   rootless conda toolchain, and runs the whole three-arm comparison as one
   job (self-hosted jobs may run 5 days; no per-arm chaining needed).

The JIT runner deregisters itself and exits when its one job ends —
completed, failed, or cancelled — which ends the SLURM job and returns the
allocation. A 30-minute idle guard in `runner-job.sbatch` covers the
cancelled-while-queued case; `#SBATCH --time` is the absolute backstop.
Write-scoped jobs (`archive`, ledger) stay on GitHub-hosted runners: the
cluster only ever holds a `contents: read` token.

## Cluster setup (once)

```sh
git clone --no-recurse-submodules <repo-url> ~/astra-sim && cd ~/astra-sim
bash ci/dcs/setup.sh          # toolchain + pinned runner into ~/astra-ci
```

Generate a dedicated key pair (`ssh-keygen -t ed25519 -f astra-ci -N ''`)
and add the public half to `~/.ssh/authorized_keys` exactly as `setup.sh`
prints — with the forced command and `restrict`.

## GitHub configuration (once)

| Kind   | Name              | Value |
|--------|-------------------|-------|
| secret | `DCS_RUNNER_PAT`  | Fine-grained PAT, this repo only, Administration read/write (mints JIT configs). |
| secret | `DCS_SSH_KEY`     | Private half of the dedicated key pair. |
| var    | `DCS_SSH_DEST`    | e.g. `jfang@comps0.cs.toronto.edu` |
| var    | `DCS_SSH_HOST_KEY`| One line from `ssh-keyscan -t ed25519 <host>` (pins the host, defeats MITM on the jitconfig hand-off). |

## Routing an experiment to the cluster

Add one field to its record in `.github/workflows/evaluation-matrix.json`:

```json
"runs_on": "dcs"
```

Entries without the field keep the hosted per-arm chain. Aggregations and
the ledger are unaffected: the cluster job uploads the same
`<artifact_name>-<run id>` bundle the hosted path produces.

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
