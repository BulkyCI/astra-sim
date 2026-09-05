# DBLP traditional-network profiles

This directory owns **separate DBLP transport profiles**. It does not add DBLP
fields to the general ASTRA experiment configuration and it does not introduce
a second ns-3 network type. Each profile projects a loss-free, no-incast
Ring-3D workload fixture onto the existing QBB/RDMA backend's already-supported
classified data-loss and bounded-recovery controls.

## Model boundary

The initial profile models one configured, receive-side data-loss source:

$$
q \in [0,1]
$$

for a defined simulated-time interval and scope. The existing backend parses
wire traffic before applying this impairment: RDMA payload data is eligible,
while ACK, NACK, CNP, and PFC bypass the configured loss model. Reliable RDMA
then either delivers the whole QP or records an explicit retry-exhausted
failure.

This is deliberately **not yet DBLP bounded-loss completion**. In particular,
there is no receiver chunk bitmap, UDP/TCP split, selective retransmission, or
residual-delivery threshold $P$. Therefore a DBLP profile must declare
`completion_contract: "reliable_full_delivery"`; it cannot configure or claim a
DBLP residual-loss tolerance.

## One impairment source

A DBLP profile's `loss_source.kind` is presently fixed to `injected_data`.
Its base workload must disable microbursts and may not configure data loss,
packet trimming, or recovery. This prevents natural buffer rejection from
becoming an unlabelled second loss mechanism.

The backend still records QBB/switch buffer drops. They are guard telemetry:
`maximum_natural_buffer_drops` fails the profile if injected loss is mixed with
queue loss. They are not added to the configured $q$ treatment.

## Profile schema

```text
schema_version: 1
name: nonempty string
base_workload_profile: repository-relative loss-free Ring-3D profile
loss_source:
  kind: injected_data
  probability: q in [0, 1]
  start_ns: nonnegative integer
  duration_ns: positive integer
  scope: all | host_to_switch | switch_to_host | switch_to_switch
  rng_stream: positive integer
  source_host/destination_host/receiver_node: optional selectors
transport_recovery:
  retransmission_timeout_ns: positive integer
  max_retransmission_retries: positive integer
completion_contract: reliable_full_delivery
expectation:
  terminal_outcome: completed | transport_failure
  minimum_data_injected_drops: positive integer
  maximum_natural_buffer_drops: nonnegative integer
```

The first checked-in profile is a deterministic liveness fixture. It injects
all in-scope data packets and expects bounded retry exhaustion, while requiring
at least one injected data drop and zero natural buffer drops. It proves only
classification, bounded terminal failure, and one-source accounting, not paper
reproduction or training accuracy.

## Run

After building the existing ns-3 target, execute:

```sh
uv run --locked python experiments/dblp/run.py \
  --profile experiments/dblp/profiles/injected_loss_retry_exhaustion_8.json \
  --output runs/dblp/injected_loss_retry_exhaustion_8 --clean \
  --simulation-timeout-seconds 60
```

A successful command means the profile's expected terminal state was observed.
For this failure fixture, the underlying simulator exits nonzero, while the
profile runner exits zero only after validating retained flow and transport
telemetry.
