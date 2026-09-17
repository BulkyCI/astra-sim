# FORGIVE: implementation notes

[forgive-spec.md](forgive-spec.md) states the rules; this file says where
each rule lives in the code, what travels on the wire, what every
telemetry column means, and which gate checks a rule against its statement.
Where this file and the specification disagree, the specification is
right. [forgive-design-plain.md](forgive-design-plain.md) says the same
rules in plain words with the assumptions behind them.

Joe Fang's work in collaboration with Zechen Ma.

The code is C++17 under `extern/network_backend/ns-3` and
`astra-sim/network_frontend/ns3`, and Python 3.11 under
`experiments/ring_3d`. Notes are current at main `59cf16c` and ns-3
`3e11ace49`.

## 1. The split between the transport and the experiment layer

The ns-3 transport carries no application semantics: it hands over a
five-tuple and a byte range and learns an answer, and it reads no step, no
phase and no budget. Every rule the specification states lives in
`astra-sim/network_frontend/ns3/ExperimentConfig.hh`, which the transport
reaches through the callbacks in
`astra-sim/network_frontend/ns3/entry.h`.

| the rule | the transport asks | the experiment layer answers |
| --- | --- | --- |
| forgive a trimmed range | `RdmaHw::ReceiveTrimmedData` | `recovery_verdict` to `evaluate_forgiveness` |
| the budget-gone report | `RdmaHw::AllowanceGone` | `allowance_gone` to `note_holes` |
| credit an arrival | `RdmaHw::ReceiveUdp` | `data_accepted` to `note_delivered` |
| the grant's eligible mark | `RdmaHw::Setup`, once per receive queue pair | `forgiveness_eligible` to `exemption_eligible` |
| the step stop's remainder | `RdmaHw::AskRemainderOnArrival` | `remainder_verdict` to `evaluate_remainder` |

Three domains share one budget and one accounting rule, so they compare at
equal budget: `admission` sheds whole messages at the sender and is the
matched baseline, `recovery` forgives at the receiver under its controller,
and `recovery_exempt` adds the licence to ignore the controller. The names
are `SheddingDomain` in `ExperimentConfig.hh` and
`selection_policy.domain` in a profile.

## 2. The ledger and the verdicts

`StepLedger` is one receiving rank's cell for one step and
`ForgivenessLedger` is the dense table over (rank, step), both in
`ExperimentConfig.hh`. A cell keeps `eligible`, `shed`, `forgiven`,
`delivered`, `owed`, `holes`, `collectives`, `completed`, and a
`SenderShare` of `owed` and `delivered` per sender. Every counter is
monotone except `holes`, which falls as repairs land.

| what moves the cell | the call |
| --- | --- |
| a message launches toward the rank | `register_eligible`, which throws if the plan never named the cell |
| the sender's baseline sheds a message | `register_shed` |
| a receiving NIC accepts payload | `register_delivered`, credited to the cell and to the sender |
| the plan opens the step | `register_owed`, `register_collectives` |
| a flow's missing bytes change | `replace_holes`, which keeps the cell's sum |
| the cap's base becomes the plan | `use_owed_base`, once, from the parser |

The pure core is a set of total functions on a cell, with no clock and no
network in them: `affords_soft` (the soft cap of the specification's trim
rule), `paces_out` and `range_coin` (the coin), `budget_gone` (the
report), `trim_verdict`, `sender_stopped` and `remainder_verdict`.
`evaluate_forgiveness` and `evaluate_remainder` are the shells that
resolve the cell, draw the coin, store the answer back and count.
`step_threshold` resolves `p_low`, `p_high` or zero from the mask, and
every path resolves it through that one function.

`Pacing` is `std::variant<NoPacing, Bernoulli>`, so a Bernoulli
probability exists only under Bernoulli and a third rule fails to compile.
`parse_pacing` in `ExperimentConfig.hh` and `_load_pacing` in
`experiments/ring_3d/generate.py` are its two smart constructors.

## 3. The report and the grant

`budget_gone` is the specification's transition inequality,
`forgiven + holes + 4096 > p x owed`, evaluated wherever an
acknowledgement or a repair request leaves the receiver. It is not a
latch: `forgiven` only grows, the holes drain as repairs land, and a cell
that reported gone reports room again once the fabric recovers.

`RdmaHw::FollowAllowanceReport` is the sender's whole share of the
protocol. It reads the two bits, counts a transition when the bit
differs from the one before it, and moves the queue pair between
withholding and delivering. The first report with the eligible bit set
and the gone bit clear is the grant, timestamped in
`cc_exempt_granted_ns`. Under `selection_policy.reengage = false` the
sender still carries and counts every report and ignores a set bit, which
is the reference arm.

`exemption_eligible` is what the receiver marks its acknowledgements
with. It reads no cell and spends no budget: a critical step marks like
any other, and its small `p` is what brings the controller back.

## 4. The stop

`note_delivered` returns true on the arrival that carries a sender past
`1 - p` of its share. `entry.h::stop_sender_flows` then walks the active
flow registry and calls `RdmaHw::StopFlow` on every open flow from that
sender into the rank, because a flow waiting on a repair receives nothing
and would otherwise wait for its own timeout. Each of those runs
`AskRemainderOnArrival`, which asks `evaluate_remainder` with the
cumulative sequence and the bytes already accepted above it; the hole is
the flow size less both, since under selective repeat a stalled flow keeps
accepting packets past its gap.

`remainder_verdict` grants the whole hole or nothing, and only when the
step's pool affords it, `forgiven + remainder <= p x owed`. A grant
absorbs everything from the cumulative sequence to the flow size and
acknowledges it, so the sender completes through the `IsFinished` it
already had, with no new packet type and no new sender state. A refusal
emits nothing. The coin never applies here.

## 5. The plan and the certification

`owed` comes from ASTRA-sim's own collective code before the first launch.
`AstraSimNetwork.cc::install_collective_plan` walks every rank,
`Workload::plan_dp_all_reduce` finds that rank's DP All-Reduce nodes, and
`Sys::plan_all_reduce_bytes_per_peer` runs the scheduler's own phase
builder on a copy of the queue allocator. Rank `r`'s answer for peer `p`
becomes `p`'s owed from `r`. One call installs the whole table through
`ExperimentConfig.hh::install_collective_plan`, because a cell whose
senders are still being added would measure its report against a total
that is not yet the total. A real receiver reads the same table from its
collective library at step start.

`ForgivenessLedger::note_collective_completed` fires on every DP
All-Reduce completion at a rank and asserts on the last one the plan
named: the launches equal the plan, and `shed + forgiven <= p(step) x
eligible`. `affords_soft` makes both throws unreachable; they are what
stops a later change to the verdicts, the remainder path or the ledger
from shipping a run that broke the contract.

`experiments/ring_3d/analyze.py::_check_ledger_law` recomputes the same
law per cell from the run's own telemetry and its own `clr_mask.csv`, and
`_require_lawful_ledger` fails the arm rather than reporting it.
`min_delivered_share` is the smallest `1 - (shed + forgiven) / eligible`
over cells with eligible bytes, and `worst_cell` names its rank and step.

## 6. The guard at the three dispatch sites

`RdmaHw::DeliverCongestionSignal` is one boolean test on the queue pair's
exemption, and it is checked at the three places the transport hands a
congestion signal to whichever controller is configured, all in
`rdma-hw.cc`:

1. a CNP-marked acknowledgement under `cc_mode` 1, before `cnp_received_mlx`;
2. the per-acknowledgement dispatch of `cc_mode` 3, 7, 8 and 10;
3. a trim notification under `cc_mode` 1.

No line inside a controller changes, and an exempt flow runs no controller
code at all. The controller raises its own rate on its own timers when it
hears nothing.

## 7. The wire

Two flag bits on the existing acknowledgement and repair request, in
`qbb-header.{h,cc}`: `FLAG_ALLOWANCE_EXHAUSTED` (the budget is gone) and
`FLAG_FORGIVENESS_ELIGIBLE` (this flow may be exempt), set by
`SetAllowanceExhausted` and `SetForgivenessEligible`. The stop is an
ordinary acknowledgement whose sequence number is the flow's size. The
data path gains nothing.

## 8. Configuration and refusals

A profile names `selection_policy` with `p_low`, `p_high`, `domain` and
the four receiver policies `pacing` (`none` or `bernoulli` with its `p`),
`cap_base` (`accounted` or `owed`), `step_stop` and `reengage`; a
`clr_schedule` of `explicit_critical_steps`; and a `network` block whose
`packet_trimming`, `transport_recovery` and `congestion_control` decide
the fabric. The four policies default to none, accounted, false and true,
and `generate.py` refuses any of them outside a forgiving domain. `recovery`
requires selective repair and `ftd` trimming; `recovery_exempt` requires
DCQCN as well, because without a controller there is nothing to be exempt
from. `RdmaHw::Setup` aborts when `Forgiveness` runs without
`SelectiveRetransmission`, when `CongestionExemption` runs without
`Forgiveness`, and when the remainder callback runs without selective
repair. `validate_experiment_contract` requires a mask covering every
step, because a step the mask does not define forgives nothing and an arm
that forgave nothing by omission reads as a real negative result.
`run.py --domain` overrides the profile's domain, which is how
`compare.py` builds the matched runs.

## 9. Telemetry

Per flow, in `telemetry/flow_events.csv`:

| column | meaning |
| --- | --- |
| `forgiven_bytes` | bytes the receiver accepted without seeing them, trims and remainders together |
| `forgiven_ranges` | trimmed ranges forgiven; a remainder was never trimmed and does not count here |
| `forgiven_remainder_bytes` | the subset of `forgiven_bytes` the step stop took |
| `pacing_refusals` | trimmed arrivals the coin declined that the cap could have afforded, so coin and cap refusals decompose without overlap |
| `soft_refusals` | bytes the soft cap declined for want of vested allowance |
| `late_forgiven_bytes` | bytes that arrived for an already forgiven range; the charge stands, so the loss the training side saw is `forgiven_bytes` less this |
| `delivered_bytes` | `physical_bytes` less `forgiven_bytes`; `physical_bytes` stays the offered figure because it joins `fct.txt` and denominates W |
| `cc_exempt` | the receiver granted this flow an exemption at some point; never withdrawn, because the telemetry is the record of the grant |
| `cc_exempt_granted_ns` | when the first acknowledgement carrying the grant arrived; zero means never |
| `cc_signal_withheld` | congestion signals the sender kept from its controller |
| `allowance_gone_reports` | reports that said the step's budget was gone |
| `cc_transitions` | reports that changed the bit |
| `cc_obeying_ns` | simulated time the sender spent delivering signals while holding a grant |

Per run, in `ns3/transport_summary.csv`: `trim_ftd_admission` and
`trim_ftd_lasthop_admission` (bytes trimmed), `trim_forgiven` and
`remainder_forgiven` (bytes forgiven), and the control-plane counts
`rto_fired`, `cnp_taken`, `cc_signal_withheld`, `allowance_gone_reports`,
`cc_exempt_granted`, `cc_transition`, `clipped_trim`.

Derived by `analyze.py` and `report.py`, never counted: trimmed-forgiven
bytes (`forgiven_bytes` less `forgiven_remainder_bytes`), the loss the
training side saw (`forgiven_bytes` less `late_forgiven_bytes`),
`forgiven_remainder_unsent_bytes` (the remainder no sender put on the
wire), the trim ratio W, the net trim ratio W', and the ledger law with
`min_delivered_share`. Do not quote `wire_per_offered`; it counts bytes
per hop rather than per receiver.

## 10. What the gate proves

`experiments/ring_3d/forgiveness_smoke.sh` runs on every push, and
`check_forgiveness.py` reads each run back off its own telemetry.

| fixture | what it must show |
| --- | --- |
| `RdmaRangeAlgebra` | the core laws directly: a cell that has accounted for everything it does not spend affords exactly its threshold's share, the law is monotone in delivered and in forgiven, a cell that has received nothing forgives nothing, the coin repeats per (flow, range, attempt), the remainder is whole or nothing, a coin refusal reports no spent allowance; plus the range clipping's straddle and partial-overlap branches, which no fabric run reaches |
| `forgiveness_smoke_8`, against the same profile in `admission` | every flow completes, forgiven bytes appear only on gradient payload and only within the law, bytes charged equal bytes absorbed, delivered bytes exclude forgiven bytes, W' is below W, two same-seed runs are identical |
| `forgiveness_race_8` | with the timeout an order of magnitude below the round-trip time, retransmitted data races the forgiveness that made it redundant and loses |
| `forgiveness_dcqcn_8` | a forgiven trim still costs a rate cut |
| `exempt_smoke_8` | only eligible gradient flows are exempt; no flow is exempt from its first byte, since a sender obeys for the round trip before its first acknowledgement; at least one signal is withheld and no non-exempt flow withholds any; a flow that changed its report was told its allowance was gone; a flow back under its controller took a rate cut afterwards |
| `bernoulli_smoke_8` | a coin refusal of a range the cap could have afforded, without which the rule cost the arm no forgiveness |
| `stepstop_smoke_8` | a forgiven remainder, charged remainder equal to the transport's `remainder_forgiven`, remainder never sent within remainder charged, ledger law verified |
| `check_single_arm_join.py` | one `run.py` arm reproduces `compare.py`'s recovery arm at the same profile and seed, byte for byte |
| `check_refusals.py` | each required field broken in turn is refused by name and leaves no telemetry |

Unit tests cover the profile parser's refusals, the construction of the
four matched runs, the counters reaching the summary and the report, and
the CI matrix's run counts.

## 11. Cost

The trim verdict is one lookup in the active flow registry plus
constant-time access into a dense array of ranks by steps, and the
remainder question is the same lookup per accepted arrival. The exemption
is asked once per receive queue pair and the congestion-signal guard is
one boolean test. A forgiving run has fewer events overall, because a
forgiven range is never retransmitted.

## 12. What has been measured

Every number lives in [results-ledger.md](results-ledger.md), one row per
run with the code it ran, the caveat that limits it, and what replaces it;
a number is quotable only if its row says so. The per-seed rows behind the
figures are in [figure-data.md](figure-data.md), the design history of the
v2 policies and the arms that price them in
[forgive-v2-design.md](forgive-v2-design.md), and the comparison against
MLT, trimmable gradients, OptiReduce, partial-reliability transports and
deadline-aware congestion control in
[forgive-related-work.md](forgive-related-work.md).

## 13. Limits and open items

- The simulator moves bytes and holds no gradient value, so every training
  claim rests on DBLP's May GPT-2 runs.
- DCQCN only. The Ultra Ethernet default congestion control is
  window-based with a trim-triggered fast adaptation and has no model
  here, and where a fabric runs with DCQCN off the exemption has nothing
  to act on.
- One tenant. The exempt flows shared the fabric with their own job's
  tensor-parallel traffic and one background burst, so the cost of the
  exemption to another job's obedient flows is bounded by the budget and
  measured nowhere.
- Eligibility covers the gradient all-reduce whole; splitting
  reduce-scatter from all-gather needs a collective-phase field in
  `AstraSim::OperationContext`.
- The receiver never acknowledges beyond what the sender has sent, since
  without evidence of congestion such skip-ahead degenerates into
  suppression at the receiver.
- The switch has no steering role; drop-precedence steering would be an
  efficiency option with no authority over acceptance.
- Comments in `ExperimentConfig.hh` and `rdma-hw.cc` still call a refusal
  a "Pull", which the protocol no longer has; the code under them
  implements the specification.
