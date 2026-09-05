# Simulation liveness and performance discipline

Distilled from the August 2026 incident sequence in which three consecutive
CI failures looked identical ("the evaluation job timed out") but had three
unrelated causes: a transport livelock, a hot-path performance regression,
and a workload whose honest arithmetic exceeded the job ceiling. Each was
initially misdiagnosed as an insufficient time budget. Read this before
raising any timeout, and before changing any per-packet code in the ns-3
transport.

## Classify the timeout before touching a budget

A killed simulation job admits exactly three explanations. The liveness
checkpoint stream distinguishes them; the external timeout that killed the
process does not. Never raise a budget until the failure is classified.

| Class | Checkpoint signature | Correct response |
| --- | --- | --- |
| Livelock | Simulated time races far past the workload's plausible duration; `completed_qps` frozen; `active_qps` small and constant; near-empty event cadence | Fix the loop; the forward-progress deadline should have fired. If it did not, the loop found a new budget-exempt path |
| Performance regression | Wall clock per 10 ms of simulated time far above the historical pace for the same phase, with `events_delta` normal; progress counters advance on schedule | Bisect the binary, not the budget; compare `wall_ms_delta` at equal `simulated_time_ns` across runs |
| Oversized workload | Steady pace matching history, but pace × remaining simulated work exceeds the guard | Re-derive the arithmetic; shrink, split, or re-gate the workload. A budget that cannot fit the six-hour hosted ceiling is a design error, not a tuning knob |

Evidence that separates the classes without rebuilding anything:

- Every liveness checkpoint carries `wall_ms_delta` and `events_delta`.
  Per-event wall cost (`wall_ms_delta / events_delta`) is the discriminator:
  inflated cost with normal counts is a code or build regression; normal cost
  with exploded counts is a behavioral change (timer churn, retransmission
  storm).
- CPU-bound setup steps are a built-in runner benchmark. The native-runtime
  unpack is a ~500 ms gunzip of hundreds of MB; compare its duration across
  runs before blaming infrastructure. In the August incident it proved the
  runner healthy while the simulator ran 93× slow.
- Uploaded artifact size per simulated millisecond approximates trace volume
  and therefore packet count. A 93× wall slowdown with normal bytes-per-
  simulated-ms rules out an event-count explosion without any rebuild.

## Hot-path discipline for the ns-3 transport

The per-packet call chain executes millions of times per simulated
millisecond. The named hot functions are `ReceiverCheckSeq`, `ReceiveAck`,
`GetNxtPacket`, `GetBytesLeft`, `RdmaEgressQueue::GetNextQindex` (which calls
`GetBytesLeft` per registered queue pair per dequeue opportunity),
`SwitchNode::SendToDev`, and `SwitchNotifyDequeue`. Rules, each learned at
cost:

- Any work added to these paths must be O(1) amortized. A loop whose trip
  count depends on a configurable ratio is a latent collapse: the milestone
  catch-up loop iterated `payload / L2_ACK_INTERVAL` times per in-order
  packet, which is 4,096 iterations at the interval of 1 that every
  evaluation profile uses. Functionally correct, invisible to every test,
  ~93× wall slowdown in CI.
- Container walks and mutations need a cheap emptiness guard before entry
  even when the container is "almost always empty": the guard is one
  comparison; the walk is a function call, iterator setup, and potential
  mutation per invocation, multiplied by the scan width of `GetNextQindex`.
- Feature-flag guards protect semantics, not cost. Code behind
  `m_selective_retransmission` still pays its data-structure costs (larger
  objects, per-call map checks) when the flag is off; measure the flag-off
  path, not just the flag-on path.
- Correctness tests cannot catch a 90× slowdown. Any change to a hot-path
  file needs a pace measurement: one liveness checkpoint interval of the
  flagship profile against the previous binary is sufficient and takes
  minutes locally.

## Liveness is bounded by progress, not by signal counts

The retry-budget history repeated the same mistake twice: bounding recovery
by counting signals. A budget counting trim notifications fails healthy
queue pairs at the sender's own send rate during any sustained blockade (no
constant survives); exempting those signals then leaves recovery loops
unbounded, because every recovery event cancels the RTO and re-arms nothing
once `snd_nxt == snd_una`, so the budget's only trigger never fires. The
durable invariant is the forward-progress deadline: a queue pair whose
`snd_una` has not advanced within `no_progress_timeout_ns` of simulated time
is dead regardless of which signals keep arriving. Signals prove the path is
alive; only cumulative acknowledgement proves the transfer is.

Corollary for any future recovery mechanism: when adding a new feedback
signal, ask what bounds a loop made entirely of that signal. If the answer
is a count, it is wrong in one direction or the other; make it a
progress-per-simulated-time bound.

## Failures must carry their own diagnosis

CI kills processes at timeouts and destroys the distinction between slow,
stuck, and legitimately long. Everything learned in the August incident that
was learned quickly came from artifacts the run had already produced; every
slow step was a fact the process took to its grave.

- Terminal transport failures report a machine-readable `failure_reason`
  plus the queue pair's counters (`snd_una`/size, recovery events, trim
  notifications). A failure line must let the reader name the sustaining
  condition without reproducing the run.
- The liveness checkpoint is the profiler of record. Do not remove or thin
  `wall_ms_delta`/`events_delta`; they cost nothing and converted a
  four-hour opaque failure into a one-line diagnosis.
- Budget notes in `evaluation-matrix.json` must record the provenance of any
  measurement they cite (commit and run). The sentinel's "2.75 h measured
  arm" note silently went stale across a code change and a three-arm
  redesign, turning a budget into fiction; the 2026-08-07 run measured the
  same arm at ~7.8 h.
- Re-run the budget arithmetic whenever the number of arms, the step count,
  or the workload scale changes. The three-arm anchoring made two budget
  chains arithmetically impossible (3 × 2.75 h > 6 h) and nobody noticed
  until the jobs failed.

## The decisive experiment is a local A/B, not deeper reasoning

Static cost estimation was wrong by ~50× in the August incident; two
same-machine builds differing by one commit settled in an hour what a day of
log forensics could not. The full verified procedure, from a bare-bones
Ubuntu machine with no root and no preinstalled protobuf/boost/MPI to a
running binary, with the entire toolchain ephemeral under `/tmp`, is
[rootless ephemeral build](rootless-ephemeral-build.md). The A/B itself:
build, measure one or two liveness checkpoints against a materialized
profile, check out the comparison submodule commit in place, rebuild
through ccache, re-measure, and compare `wall_ms_delta` at equal
`simulated_time_ns`. Architecture does not matter for a relative
comparison; the incident's regression reproduced on aarch64 at ≥7× against
an x86 CI signature of 93×.
