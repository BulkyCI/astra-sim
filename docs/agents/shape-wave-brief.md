# The shape wave: builder's brief

Written 2026-09-18. Four rules for spending the vested budget, each a
one-line alternative in the receiver's forgive-now decision, run against
linear vesting on the worst cell at budget 0.1, three seeds, and read with
one new counter. Every arm has its kill test written here before dispatch;
a rule that fails its test is deleted in the commit that records the
reading. Joe Fang's protocol; the coin and the head start are Yashar
Ganjali's suggestions; the head-start size is set by the fabric, never by
a packet count.

## 1. Why

Under vesting the coin no longer moves time, so what is left to learn
about the soft cap is whether forgiveness buys any time at all on a
selective-repeat fabric, and if it does, whether spending it where the
fabric is worst buys more. The line through the origin forgives 18 % of
the trimmed bytes that arrive in the first fifth of a step and 60 % of
those in the last, while the first fifth trims seven times more than the
last. Nothing built so far spends by fabric state.

## 2. The arms

All at `p_high = 0.1`, `p_low = 0.005`, critical steps 1, 2, 3 and 20,
`direct7` at 4:1 with DCQCN, seeds 9550582, 23172535 and 94081284, no
coin, no stop, joined against run #123's fixed-low control and run #127's
`p01_single` arm.

| arm | the forgive-now rule | what it asks |
| --- | --- | --- |
| control (in hand, #127 `p01_single`) | `forgiven + range <= p x (received + forgiven)` | |
| `p0` | Bernoulli at `P = 0`: never forgive; the licence and the gone rule unchanged | does forgiveness buy time at all, or is the tolerance only the bound on the licence |
| `holes` | `forgiven + range <= p x (received + forgiven + holes)` | does borrowing against bytes in flight, repaid when they land, buy time per byte lost |
| `head` | `forgiven + range <= c + s x received`, with `c = k x p x owed`, `s = (p x owed - c) / ((1 - p) x owed)` | does a round trip of tolerance at the start move the front |
| `second` | forgive only a range whose trim header ends at or below the flow's `highest_seen_end`, then under the control's rule | does forgiving only what the fabric has already lost twice keep the time at a fraction of the loss |

The head start's size is the fabric's: `k = senders x BDP / owed`, seven
senders on this cell, BDP from the topology file (400 Gbps and the
configured link and endpoint delays), `owed` per cell 149 536 100 B. The
profile states `k`; the builder computes it once and writes the value and
its derivation in the profile's comment.

## 3. Code

1. `experiments/ring_3d/generate.py`: the pacing constructor admits
   `p = 0` under `bernoulli` (today it requires strictly between 0 and 1);
   the C++ side already refuses every coin at threshold 0. Add
   `selection_policy.cap_shape` with cases `linear` (default), `holes`,
   `head` (with `k`), `second`; one sum type, one field per case that
   needs one.
2. `astra-sim/network_frontend/ns3/ExperimentConfig.hh`: `affords_soft`
   takes the shape. `holes` adds `cell.holes` to the base. `head` adds
   `c` and uses slope `s`. `second` is a guard before the rule: a range
   whose trim header ends at or below the flow's `highest_seen_end` at
   arrival is a retransmission trimmed again (per-flow ECMP keeps a
   flow's packets in order); refuse otherwise. The hard cap, the gone
   rule, the eligible bit and certification do not change.
3. The counter: `repeat_trims` and `repeat_trim_bytes` per flow, counted
   by the same comparison, in the per-flow CSV and summed by the
   analyzer; also count them on the control by running the comparison
   under every shape.
4. `experiments/ring_3d/analyze.py`: the ledger law is unchanged
   (`forgiven <= p x owed` per cell, delivered share at least `1 - p`);
   add the two columns and a per-step split of `soft_refusals` and
   forgiven bytes by fifth of the step's received bytes, so the front
   bias is read at trim level rather than by flow start.
5. Profiles: `regime_64_dcqcn_direct7_4to1_exempt_p01_{p0,holes,head,second}`
   with matrix records under gate `forgive_v2`, filter `shape`.
6. Smoke: `forgiveness_smoke.sh` runs each shape on the bucketed profile
   and the fixtures in `scratch/rdma-range-algebra.cc` gain one case per
   shape.

No new wire bits, no new per-cell state beyond what `holes` already
keeps, no spec change until an arm earns it.

## 4. Kill tests, written before dispatch

| arm | killed if | then |
| --- | --- | --- |
| `p0` | time within the seed spread of the control's 16.1 to 16.7 % | forgiveness has no time value on this fabric; the shape question is loss only and moves to go-back-N; the paper's claim sharpens to "the tolerance bounds the licence" |
| `holes` | time per byte lost not above the control's, or first-fifth forgiven share up by under 10 points | delete |
| `head` | first-fifth forgiven share up by under 5 points, or up with time inside the seed spread | delete the shape and `k` |
| `second` | loss not below the control's by at least a third, or time below the control's by more than the seed spread | delete |

The seed spread on this cell is the zero-tolerance reference's -1.1 to
+0.8 % of the control.

## 5. What is read

Per arm and seed: window makespan against the control, forgiven bytes as
a share of DP bytes after late arrivals, re-sent bytes, repeat-trim bytes
as a share of trimmed bytes (on every arm including the control), the
forgiven share by fifth of received bytes, TP collective time against the
control, transitions and obeying time per exempt flow, and the certified
worst cell. The repeat-trim share on the control is the ceiling for any
timing rule's load channel; below about 1 % of bytes, `p0` is expected to
hold and the other three arms are expected to read "same".

## 6. Order

Build all four, one smoke run each, one commit with `[skip ci]`, then one
dispatch. Reading order when the wave lands: `p0` first, because its
answer decides how the other three are read.
