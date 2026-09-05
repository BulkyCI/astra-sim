<!-- Source: Ultra Ethernet Consortium, Specification v1.0.3 (PDF, released 2026-07-16), and the cited papers; repo claims verified against file:line. Read 2026-09-05. -->

# UEC transport brief: congestion control, trimming, loss recovery, and our ns-3 backend

Scope note: every UEC factual claim below is sourced from the Ultra Ethernet Consortium's
own specification PDF (fetched and read directly, not from memory) or from other cited
web sources retrieved 2026-09-05. Section/page numbers refer to UEC Specification v1.0.3
(574 pages, released 2026-07-16) unless noted. Repository claims are sourced to file:line
in `/config/repositories/astra-sim`.

## Part 1: UEC transport facts

### 1. Spec status and structure

UEC published Specification v1.0 on 2025-06-11, v1.0.1 on 2025-09-05, v1.0.2 on
2026-01-28, and v1.0.3 on 2026-07-16 [S1][S2][S3]. v1.0.3's own release notes describe it
as editorial corrections and clarifications to v1.0.2, plus one behavioral change: removal
of the UET_TRIMMED_ACK NACK code (see §2 below) [S3 p.573-574]. This brief cites v1.0.3
page numbers throughout.

Trimming gets two treatments in the spec, at different layers:

- **Section 4.1 "Packet Trimming"** (Network Layer chapter), pp.459-464, subsections
  4.1.1-4.1.7 [S3 p.459-464].
- **Section 3.6.4.4 "Packet Trimming"** (inside the Congestion Management Sublayer
  chapter, a CC-oriented treatment of the same feature), p.356 [S3 p.356].

UEC's four transport sublayers, confirmed in the TOC and body text [S3 §1-3]:
- **SES** (Semantic Sublayer): maps RDMA/collective-library operations (sends, writes,
  reads, atomics) to wire semantics; generates SES Responses.
- **PDS** (Packet Delivery Sublayer): reliability/ordering, PDCs, ACK/NACK, retransmission,
  loss detection (RUD/ROD/RUDI/UUD modes) [S3 p.217].
- **CMS** (Congestion Management Sublayer): telemetry, NSCC, RCCC, TFC, multipath [S3 p.344].
- **TSS** (Transport Security Sublayer): encryption/authentication, replay protection [S3 p.412].

### 2. Packet Delivery Sublayer

Four delivery modes, all confirmed at [S3 p.233-235]:
- **RUD** (Reliable Unordered Delivery): each packet delivered to SES exactly once;
  delivered to SES in arrival order (not sequence order); uses selective retransmission
  and direct out-of-order data placement.
- **ROD** (Reliable Ordered Delivery): delivered exactly once, in the order SES originally
  sent them; transmitted over a *single* entropy/path. **"ROD uses GoBackN loss recovery.
  GoBackN drops all packets that arrive out of order, requiring the source to retransmit
  all packets starting from the first missing PSN."** [S3 p.233-235]. Go-back-N is
  explicitly part of UET, but only for the ordered mode, which by design forgoes
  multipath spraying.
- **RUDI** (Reliable Unordered Delivery for Idempotent operations): delivered *at least
  once* (duplicates allowed), no PDC/connection state, no ACKs: uses NACKs for early loss
  detection and per-packet RUDI responses [S3 p.233-235]. RUDI is **reliable**, not a
  "deliver what arrived" mode (see §7).
- **UUD** (Unreliable Unordered Delivery): a basic best-effort datagram service, no ACKs,
  not congestion-controlled by UET-CC [S3 p.233-235]. Its send opcode,
  `UET_DATAGRAM_SEND`, is single-packet-message only, with message ID fixed at 0
  [S3 p.157].

SACK: `pds.sack_bitmap` is a **64-bit** field; each set bit marks a received/processed PSN
relative to `SACK_Base`; a cleared bit means "no information," not "not received": the
bitmap is a redundant, best-effort signal layered on top of the cumulative ACK (`CACK_PSN`)
[S3 p.280, §3.5.11.14]. Retransmission is triggered by three independent mechanisms, all
"MUST": trimming (single-RTT), explicit NACK, and RTO as backstop [S3 p.290-297]. NACK
codes `UET_TRIMMED` (0x01) and `UET_TRIMMED_LASTHOP` (0x02) are defined exactly as our code
assumes [S3 p.290-291, Table 3-58]. `UET_TRIMMED_ACK` (0x03) is reserved: a trimmed RUD or
ROD ACK generates no NACK at all; the source relies on RTO to notice the missing ACK and
retransmit the original request [S3 Table 3-58, Table 3-61, p.297]. RTO uses exponential
backoff: `RTO_TIMER = RTO_INIT_TIME * 2^retry_count`, range 0–8 s [S3 p.290, p.297].
Packet spraying places each packet on a pseudo-randomly chosen entropy value from a pool
of 64–256 entropies, reacting to ECN/trim feedback per path [S3 §3.6.5.2]. A PDC (Packet
Delivery Context) is a dynamically established, ephemeral FEP-to-FEP connection created
with zero round-trip startup cost and torn down when idle [S3 §3.4].

### 3. Packet trimming

Verified against the spec text directly [S3 §4.1, p.459-464; §3.6.4.4, p.356]:
- DSCP_TRIMMABLE / DSCP_TRIMMED (and optional DSCP_TRIMMED_LASTHOP) are real, spec-defined
  codepoints; the operator configures the mapping, values are not fixed by the spec
  [S3 p.460-464].
- Trimmed size floor is `MIN_TRIM_SIZE`; Table 4-1 gives **24 B for UET/UDP/IP** (UDP 8 B +
  PDS request header 16 B) [S3 p.464]: this matches our repo's default `min_trim_size_bytes
  = 24` exactly.
- TC_med bandwidth share: **"Fair-queueing allows trimmed packets to consume no more than
  50% of the bandwidth... WDRR with 25% of the bandwidth allocated to trimmed packets is
  also a good configuration option, at the expense of moderate trimmed packet loss in
  large incasts."** [S3 p.463]. Our repo's "25% WDRR recommended, 50% cap" is verified correct.
- **Back-to-sender is explicitly out of scope**: "This specification focuses only on
  sending the trimmed packet to the destination. Sending a trimmed packet back to the
  source... is not part of this specification." [S3 p.459]. Confirms our repo's "ftd is
  the specified behavior, bts is research-only" claim.
- Trimming is a congestion **signal**, but a conditional one for the last hop: **"[a
  DSCP_TRIMMED_LASTHOP packet] is not used as a congestion signal to NSCC *when RCCC is
  also enabled*, because RCCC can handle last-hop congestion by itself."** [S3 p.356]. The
  exclusion in the spec is conditioned on RCCC being present: see the gap this creates in
  Part 2 §4.

### 4. Congestion control: NSCC, RCCC, comparison to DCQCN, and recommended defaults

**NSCC** (Network Signal-based Congestion Control) is **window-based**, not rate-based:
it maintains `cwnd` and permits sending only while `inflight + MTU <= cwnd`; ACKs report
`Rcvd_Bytes`, which "clocks" `inflight` down [S3 p.384, §3.6.13]. It is a dual-signal
algorithm using both ECN and measured queuing delay (`RTT − base_RTT`), producing four
cases (uncongested → proportional/fast increase; ECN clearing → fair/additive increase;
ECN set + low delay → hold; ECN set + high delay → multiplicative decrease) plus a
`quick_adapt()` fast-reaction path triggered directly by loss/trims or excessive delay,
which sets `cwnd` from measured achieved goodput rather than halving it [S3 p.384-393,
§3.6.13.5–.6]. On a trim-triggered NACK, NSCC treats it like an ECN mark for `quick_adapt`
purposes and applies a discrete `cwnd -= nominal_pktsize` decrease: explicitly **only if
RCCC is not also handling the last hop**: `"if reason == UET_TRIMMED or (reason ==
UET_TRIMMED_LASTHOP and rccc == FALSE): adjust_cwnd = TRUE"` [S3 p.393]. NSCC's spec text
is explicit about *why* it avoids a rate-based design: **"in contrast, in a rate-based
approach such as DCQCN, lack of feedback is implied to be a sign of appropriate network
operation, and the rate is increased. This approach works in lossless networks, where
PFC kicks in as a backstop, but in best-effort networks where packets may be silently
discarded due to congestion, increasing throughput in response to a lack of congestion
feedback results in poor performance."** [S3 p.365, §3.6.5.3]. NSCC is based on the
SMaRTT and STrack research algorithms, named at [S3 p.384] and cited in full at
[S3 p.456] [S4][S5].

**RCCC** (Receiver-Credit Congestion Control) is derived from EQDS [S6] and is optional,
usable alone or alongside NSCC. Each source holds a credit balance; it may send only while
credit > 0; the destination paces credit to all active sources at (near) link rate via
Credit CPs / ACK-carried credit, based on sources' advertised `credit_target` backlog
[S3 p.399-400, §3.6.14]. This is the explicit UET mechanism for incast: **"To deal with
incast, RCCC leverages information available at the destination to make optimal,
instantaneous changes to the transmission rate of each of the active sources."**
[S3 p.399]. When RCCC is enabled, ECN on the last hop is disabled by recommendation,
because RCCC already manages that hop directly and NSCC would otherwise double-react
[S3 p.400].

**Recommended parameter defaults** (all from §3.6.13/§3.6.17, pp.390-419): `config_base_rtt`
is the round-trip time of the longest-path MTU-sized packet with no other traffic,
maintained to the nearest 128 ns (p.390). `BDP = min(sender.linkspeed, receiver.linkspeed)
* config_base_rtt` (p.390). `target_qdelay` defaults to `0.75 * config_base_rtt` when
trimming is used, `1.0 * config_base_rtt` otherwise (p.390).
`alpha = 4.0 * scaling_a * scaling_b * MTU / target_qdelay` (p.390). `max_wnd = 1.5 *
sender.linkspeed * base_rtt` (p.397) is the default initial `ccc.cwnd` (Table 3-83,
pp.390-391). `qa_threshold`, the quick_adapt delay trigger used only when trimming is
disabled, is `(drop_threshold / Plane_BDP - 1) * config_base_rtt`; with the recommended
tail-drop threshold of `5 * Plane_BDP` this equals `4 * target_qdelay` (p.390). Switch-side
(pp.418-419): probabilistic ECN marking `queue_low.min_thresh = 0.2 * Plane_BDP`,
`max_thresh = 0.8 * Plane_BDP`; deterministic ECN threshold `0.5 * Plane_BDP`
(probabilistic preferred); trim threshold `Plane_BDP` for normal queues and `1.5 *
Plane_BDP` for the last-hop queue; drop thresholds `queue_med.drop_threshold =
queue_high.drop_threshold = Plane_BDP`, general tail-drop threshold recommended between
`2 * Plane_BDP` and `5 * Plane_BDP`. These size NSCC's window and switch queues for
whatever link speed and base RTT a simulator uses, rather than hand-picked fixed
constants.

**Comparison to DCQCN / our mode 1**: DCQCN (`cnp_received_mlx`, `RATE_AI`/`RATE_HAI`,
`ALPHA_RESUME_INTERVAL`, `RATE_DECREASE_INTERVAL`, `EWMA_GAIN`: `rdma-hw.cc:1002-1122`)
is **rate-based, EWMA-averaged, single-signal (ECN/CNP)**, with a fixed multiplicative
decrease (`rate *= 1 − alpha/2`) and staged additive/hyper increase: the architectural
opposite of NSCC on the exact axis the spec cites as the reason best-effort lossy
networks need a different design. **Using DCQCN with trims mapped to CNPs is a reasonable,
cheap first sender-reactive-CC arm: it is not a stand-in for NSCC.** It misses
quick_adapt's loss-aware fast convergence, delay-based congestion detection (DCQCN never
reacts to RTT), the ACK-clocked window semantics that make NSCC safe on a lossy fabric,
and any incast-specific mechanism (DCQCN has none; that is RCCC's job). Known DCQCN
weaknesses in the wider literature include slow convergence and a historical dependence
on PFC as an implicit backstop against silent loss [S7].

### 5. Public simulators / reference models for UET

- **SMaRTT-REPS** [S4] (arXiv:2404.01630, Bonato et al., April 2024): the paper the spec
  cites as NSCC's direct source [S3 p.384, full citation p.456]. Built on **htsim** (not ns-3), evaluated on
  synthetic fat-tree topologies (1024-node non-blocking and 2:1/4:1/8:1 oversubscribed,
  plus a 128-node tree), 4 KiB MTU, 800 Gb/s links, 400 ns switch latency. Models trimming,
  NSCC's precursor algorithm, and REPS adaptive spraying; reports incast FCT inflation
  relative to a theoretical optimal for SMaRTT and RoCEv2/DCQCN, and shows SMaRTT
  outperforming EQDS/Swift/BBR/MPRDMA by up to 50%. It does **not** report anything
  equivalent to our `W = re-carried bytes / offered bytes`, so no direct numeric transplant
  is possible: only qualitative confirmation that trimming plus a delay-aware CC keeps
  incast close to optimal.
- **EQDS** [S6] (Olteanu et al., NSDI'22): the paper RCCC derives from. Reports near-perfect
  incast with small in-network queues, 2x TCP FCT improvement, ~30% NVMeoF throughput gain,
  and 10–30x memcached speedup: again not expressed as a re-carried-bytes ratio.
- **REPS** [S8] and **STrack** [S5] are the other two papers the spec cites by name for
  adaptive spraying and multipath reliability [S3 p.384, p.456]; not deep-read beyond
  abstract/citation record: treat any numeric claim from them as **unverified**.
- **No dedicated ns-3 UET module** was found in public circulation as of 2026-09-05.
  **Unverified**: whether any UEC member has a non-public one.

None of these sources report a metric in the same units as our canary, so **there is no
apples-to-apples external number for "the cost of a lost packet on a UEC fabric"**.
Only qualitative confirmation that trimming plus NSCC/RCCC keeps that cost small relative
to a no-CC or DCQCN-only baseline.

### 6. Deployment reality, 2024–2026

- **AMD Pensando Pollara 400GbE**: shipping, UEC-aligned; AMD claims (per press coverage)
  10% higher RDMA performance than NVIDIA CX7, and that UEC 1.0 features (load-balancing,
  selective retransmission, path-aware CC) can improve RDMA performance ~25% over
  traditional RoCEv2. Pensando Vulcano (800G, PCIe Gen6) is announced for 2026 [S9][S10].
- **Broadcom Thor Ultra**: announced as the "industry's first 800G AI Ethernet NIC," UEC
  1.0-compliant, with packet-level multipathing, out-of-order direct-memory placement, and
  selective retransmission; Hot Chips 2026 disclosed 781 Gb/s unidirectional and
  1558 Gb/s bidirectional RDMA throughput on an 800G/1.6T link [S11][S12].
- **NVIDIA Spectrum-X / ConnectX-8**: NVIDIA's stated strategy is proprietary
  scheduling/CC (Spectrum-X) rather than UEC-first; ConnectX-8 is positioned as an
  800G-class Thor Ultra competitor. **Unverified**: whether Spectrum-X/ConnectX-8
  implements UEC-conformant trimming specifically, vs. NVIDIA's own adaptive-routing stack.
- **ConnectX-6/7 default behavior**: classic RoCEv2 NICs default to go-back-N; "Selective
  Repeat" exists from ConnectX-6 DX onward but has documented gaps: it does not combine
  with adaptive routing/tag-matching on ConnectX-6, and a developer-forum report says it
  "does not seem to work on CX-7 NICs even enabled in mlxconfig" [S13][S14]. Academic
  motivation papers (IRN, SRNIC, Flor) independently describe mainstream RoCE as go-back-N
  by default, treating selective-repeat as a research/limited-availability improvement
  [S15][S16][S17].

### 7. Unreliable/lossy application semantics in UET

**RUDI is not the unreliable mode.** It is *reliable* (at-least-once) delivery for
idempotent operations; every RUDI request still gets NACK'd and retried on loss
[S3 p.233-235]. The mode that matches "deliver what arrived, no repair" is **UUD**
(Unreliable Unordered Delivery): "a basic datagram service. An unreliable datagram
service enables best-effort delivery... There is no acknowledgement for the unreliable
delivery mode." [S3 p.233-235]. UUD is explicitly **not controlled by UET-CC**, and the
spec places the burden of avoiding self-inflicted congestion on the application if UUD
shares a traffic class with RUD/ROD [S3 p.233-235]. Its send opcode is single-packet-message
only, message ID fixed at 0 [S3 p.157]. UUD is the natural spec-level home for a
bounded-loss gradient transport's data plane, a genuine "fire it and accept what arrives"
primitive, unlike RUDI, which still repairs everything, just without ordering or
duplicate-suppression guarantees.

---

## Part 2: mapping onto our ns-3/ASTRA-sim backend

Files read: `docs/agents/loss-tolerant-rdma-decision.md`, `docs/agents/loss-tolerant-rdma-audit.md`,
`experiments/ring_3d/GLOSSARY.md`,
`extern/network_backend/ns-3/src/point-to-point/model/rdma-hw.cc`,
`extern/network_backend/ns-3/src/point-to-point/model/rdma-queue-pair.{h,cc}`,
`extern/network_backend/ns-3/scratch/common.h`, `experiments/ring_3d/generate.py`.

**Headline confirmed finding**: `grep` of `rdma-hw.cc` shows `m_cc_mode` is only branched
on for values `1, 3, 7, 8, 10` (mlx/DCQCN, HPCC, TIMELY, DCTCP, HPCC-Pint) at every call
site (`rdma-hw.cc:284-296, 450-462, 520-533, 635-637, 831, 854`). `generate.py:1206`
hard-codes `CC_MODE 12` in every generated network config. **Mode 12 has no branch
anywhere**: every rate/window-adjustment function (`UpdateAlphaMlx`, `cnp_received_mlx`,
`HandleAckHp`, etc.) is simply never called, so `qp->m_rate` is set once at queue-pair
creation and never changed. This matches your finding exactly: CC_MODE 12 runs a static,
line-rate window with `HAS_WIN 1 VAR_WIN 1` (`generate.py:1210`) computing the window from
a rate that is never adjusted.

| UET feature | Our backend (file:line) | Gap severity for "cost of loss" | Effort |
|---|---|---|---|
| Sender CC at all | **None**: `CC_MODE 12` unhandled (`rdma-hw.cc:284-296,450-462,520-533`; `generate.py:1206`) | **Critical.** Almost certainly the dominant driver of the trimmed/incast/W canary: line-rate sending with zero backoff maximizes both trims and re-carried bytes. | **Small**: mode 1 (DCQCN) is fully implemented, gated only by `CC_MODE`. |
| Window vs. static rate | `HAS_WIN 1`, `VAR_WIN 1` (`generate.py:1210`) computed from `m_rate` (`rdma-queue-pair.cc`) | **High**, but a consequence of the row above: a variable window over a static rate is cosmetic. | Small once CC is enabled. |
| Selective ACK (64-bit SACK bitmap) | Range-based repair instead: NACK advances one MTU of gap-head per NACK (`ReceiveAck` `rdma-hw.cc:504-515`); trim notifications carry an exact byte range (`RecoverTrimmedQueue` `rdma-hw.cc:600-651`, `AddRepairRange`/`m_repair_ranges` in `rdma-queue-pair.h`); receiver accepts out-of-order ranges via `m_ooo_ranges`/`AbsorbContiguousFrom` (`ReceiverCheckSeq` `rdma-hw.cc:680-699`) | **Medium.** Converges to selective repair on the trim path (the one that matters most), but a bare NACK only repairs one MTU at a time, so multi-packet gaps need multiple RTTs. Low priority while ECMP is flow-pinned (reordering is rare). | Medium: needs a wire-format bitmap and bitmap logic; existing repair-range machinery is a reasonable base. |
| Trimming mechanics (DSCP codepoints, MIN_TRIM_SIZE, TC_med share, ftd/bts, last-hop codepoint) | Implemented close to spec: `min_trim_size_bytes=24`, `trimmed_queue_weight=25` defaults, `ftd`/`bts` modes, `DSCP_TRIMMED_LASTHOP` (`rdma-hw.cc:565-678`; `GLOSSARY.md`) | **Low**: best-aligned part of the implementation. One real discrepancy below. | N/A |
| **Last-hop trim → CC exclusion** | Unconditional: `if (m_cc_mode == 1 && !lastHop) cnp_received_mlx(qp);` (`rdma-hw.cc:635-637`) always withholds the CC signal for last-hop trims | **Medium-high, directionally wrong for us.** Spec conditions this exclusion on RCCC being enabled [S3 p.356], because RCCC handles last-hop/incast instead. We have **no RCCC**, so withholding the signal leaves incast with nothing reacting: touches the 7×128 MiB incast canary directly. | Small: drop the `!lastHop` guard for mode 1 until an RCCC equivalent exists. |
| NSCC vs. our CC | Not implemented; mode 1 = DCQCN (rate-based, EWMA, single ECN/CNP signal, `rdma-hw.cc:1002-1122`) | **High** for any "UEC-like" CC claim: NSCC is window-based, dual-signal (ECN+delay), specifically because rate-based schemes misbehave on lossy fabrics [S3 p.365]. DCQCN-with-trims is a legitimate baseline, not evidence about UEC. | Large: new per-CCC `cwnd`/`inflight` state, RTT+ECN dual-signal logic, `quick_adapt`, wire-format additions for `Service_Time`/`Rcvd_Bytes`. |
| Receiver credit / incast (RCCC) | Not implemented (`CheckandSendQCN` declared, never called: `rdma-hw.h:60-77`) | **High** for the incast question specifically: RCCC is UET's dedicated incast mechanism; nothing analogous exists. | Large: credit protocol, `credit_target` field, destination scheduler, credit timer. |
| Multipath / spraying | Flow-pinned ECMP: 5-tuple hash picks one path per flow (`switch-node.cc:65-91`) | **High** for UET-fidelity, but **lowers urgency** of full SACK work since reordering is rare without spraying. | Large: per-packet entropy selection, adaptive path avoidance, reorder buffering (partially present via `m_ooo_ranges`). |
| RUDI-like unreliable/"deliver what arrived" mode | None: every RDMA UDP QP goes through the same reliable go-back-N/selective-repair path | **High**: biggest conceptual gap for a *bounded-loss* gradient transport, since UUD (not RUDI, see §7) is the spec's real "accept partial delivery" primitive, and we have no equivalent QP type. | Medium: a QP flag that skips retransmission/RTO while keeping classify-before-loss/control-plane isolation. |
| RTO behavior | Fixed-interval timer, no exponential backoff: `ArmRetransmissionTimeout` always schedules `NanoSeconds(m_retransmission_timeout_ns)` (`rdma-hw.cc:787-793`); retry budget via `m_recovery_retries`/`m_max_retransmission_retries` (`rdma-hw.cc:817-825`); trim notifications don't consume the retry budget (`rdma-hw.cc:611-619`) | **Medium**: spec requires exponential backoff (`RTO_TIMER = RTO_INIT_TIME * 2^retry_count` [S3 p.290]); a fixed timer under-reacts to sustained congestion. | Small: multiply the scheduled interval by `2^retry_count`. |
| NACK code taxonomy | Two effective codes (trim / trim-lasthop via a flag bit and `isFtdRepair`); no general `pds.nack_code` field or per-code delay table | **Medium**: spec defines ~26 NACK codes with per-code RETX/RETRY/FAIL semantics and a delay table [S3 p.286-291]; we distinguish only "trim" vs. everything else. | Medium: a wire-format NACK-code field and small dispatch table. |

---

## Part 3: recommendation

**(a) Turn on mode-1 DCQCN with trims-as-CNPs as the first CC arm: yes, but with two
fixes, not as-is.** Since CC_MODE 12 runs no congestion control at all, enabling *any*
sender-reactive scheme is likely to move all three "remaining cost" hypotheses (re-carried
bytes, rate cuts, RTO waits) simultaneously, because nothing currently throttles offered
load into the trimming fabric. Two changes first:

1. **Drop the `!lastHop` guard at `rdma-hw.cc:635`.** The spec only excludes last-hop
   trims from the CC signal when RCCC is present [S3 p.356]. We have no RCCC, so leaving
   the guard in place gives the 7×128 MiB incast canary zero reaction from the one CC
   mechanism we do have.
2. **Rescale `RATE_AI`/`RATE_HAI`/`MIN_RATE` for 400 Gb/s.** `generate.py:1207-1208`
   hard-codes `RATE_AI 50Mb/s`, `RATE_HAI 100Mb/s`, `MIN_RATE 100Mb/s` as flat, ~100 Gb/s-era
   literals, unlike `KMIN_MAP`/`KMAX_MAP` which are already scaled per link speed
   (`generate.py:1217-1219`; roughly 8x higher at 400 Gb/s than at 25 Gb/s). At 400 Gb/s, a
   50 Mb/s additive-increase step is ~0.0125% of link capacity, so recovery from a decrease
   would be very slow. No UEC- or vendor-published multiplier for this was found; "scale
   roughly like KMIN_MAP/KMAX_MAP" is a heuristic, **unverified**, and should be
   validated empirically, not trusted as a calibrated value.

**(b) Yes: NSCC (or a documented substitute) needs to be modeled before any claim about
"UEC congestion behavior" can be made.** The spec frames NSCC's window/dual-signal design
as a direct rejection of DCQCN's rate/single-signal design for lossy best-effort fabrics
[S3 p.365]. DCQCN-with-trims is a fine baseline for "does some CC beat no CC," but "this
shows what UEC does under loss" is not supportable until NSCC (at minimum its `quick_adapt`
loss-aware reaction and dual ECN+delay signal) exists. Effort: **large**: comparable to
adding a new full CC mode alongside HPCC (`mode 3`): new per-CCC `cwnd`/`inflight` state,
wire-format additions for `Service_Time`/`Rcvd_Bytes` in ACKs (currently absent), the
four-branch ECN+delay logic, and `quick_adapt`. A receiver-credit (RCCC) implementation
for incast specifically is a separate, comparably large piece of work.

**(c) External benchmark for "cost of loss under trimming + SR + NSCC": none of the
sources found report a metric in the same units as our canary.** There is no direct
transplant for `0.37 ms vs 0.19 ms`, the `29 ms vs 18.8 ms` incast floor, or `W = 0.02`.
The closest work is SMaRTT-REPS [S4] (htsim, 800 Gb/s, 4 KiB MTU, reports incast FCT
inflation *relative to theoretical optimal*, not absolute ms or a byte ratio) and EQDS
[S6] (near-perfect incast with small queues, 2x TCP FCT gain, ~30% NVMeoF throughput
gain: again not `W`). Both are qualitative evidence that trimming plus a reactive window
CC and/or receiver credit drives loss cost toward a theoretical floor, directionally
consistent with our own SR-vs-go-back-N canary (SR ~4x faster, loss "nearly free"), but
either paper's numbers cannot responsibly convert into a claim about our specific `W` or
ms figures: different simulator, link speed, MTU, and metric definitions throughout.
**Report the canary as internally validated and directionally consistent with the external
literature; do not claim numeric agreement.**

Overall, the most defensible next step is: (1) fix and enable mode-1 DCQCN (3a) to remove
the "zero congestion control" confound; (2) re-run the trimmed/incast/`W` canary under
DCQCN to see how much of today's cost is simply unthrottled offered load versus genuinely
rooted in loss/repair; and (3) treat NSCC/RCCC as the next increment only once (2) shows a
residual cost a sender-reactive rate scheme cannot explain: that residual is what a
bounded-loss/DBLP policy would actually be buying back on a real UEC-shaped fabric.

---

## References

- [S1] Ultra Ethernet Consortium, "Ultra Ethernet Consortium (UEC) Launches Specification
  1.0 Transforming Ethernet for AI and HPC at Scale," https://ultraethernet.org/ultra-ethernet-consortium-uec-launches-specification-1-0-transforming-ethernet-for-ai-and-hpc-at-scale/, accessed 2026-09-05.
- [S2] Ultra Ethernet Consortium, *Ultra Ethernet Specification v1.0.1* (PDF, 2025-09-05),
  https://ultraethernet.org/wp-content/uploads/sites/20/2025/10/UE-Specification-1.0.1.pdf, accessed 2026-09-05.
- [S3] Ultra Ethernet Consortium, *Ultra Ethernet Specification v1.0.3* (PDF, released
  2026-07-16, 574 pages),
  https://ultraethernet.org/wp-content/uploads/sites/20/2026/08/UE-Specification-1.0.3.pdf, accessed 2026-09-05. Page numbers above refer to this PDF's printed page numbers, which match its PDF page numbers.
- [S4] Bonato, Kabbani, De Sensi, Pan, Le, Raiciu, Handley, Hoefler, et al., "SMaRTT-REPS:
  Sender-based Marked Rapidly-adapting Trimmed & Timed Transport with Recycled Entropies,"
  arXiv:2404.01630 (2024-04-02), https://arxiv.org/abs/2404.01630, accessed 2026-09-05.
- [S5] Le, Pan, Newman, Blendin, Kabbani, et al., "STrack: A Reliable Multipath Transport
  for AI/ML Clusters," arXiv:2407.15266 (2024-07-21), https://arxiv.org/abs/2407.15266,
  accessed 2026-09-05 (title/citation only, not deep-read).
- [S6] Olteanu, Eran, Dumitrescu, Popa, Handley, Raiciu, et al., "An edge-queued datagram
  service for all datacenter traffic," NSDI'22,
  https://www.usenix.org/system/files/nsdi22-paper-olteanu.pdf, accessed 2026-09-05.
- [S7] General DCQCN literature summary via web search (slow convergence / PFC-dependence):
  no single primary DCQCN-weaknesses source pinned beyond the NSCC spec's own contrast
  text [S3 p.365], which is the authoritative citation used above.
- [S8] Bonato, Kabbani, Ghalayini, Papamichael, et al., "REPS: Recycled Entropy Packet
  Spraying for Adaptive Load Balancing and Failure Mitigation," arXiv:2407.21625
  (2024-07-31), https://arxiv.org/abs/2407.21625, accessed 2026-09-05 (title/citation only).
- [S9] Tom's Hardware, "AMD deploys its first Ultra Ethernet ready network card — Pensando
  Pollara provides up to 400 Gbps performance," https://www.tomshardware.com/networking/amd-deploys-its-first-ultra-ethernet-ready-network-card-pensando-pollara-provides-up-to-400-gbps-performance, accessed 2026-09-05.
- [S10] Yahoo Tech / press summary, "Pollara 400GbE AI NIC leads AMD's push into
  UltraEthernet networking, Vulcano 800G coming for Gen6 clusters in 2026,"
  https://tech.yahoo.com/ai/articles/pollara-400gbe-ai-nic-leads-173100063.html, accessed 2026-09-05.
- [S11] ServeTheHome, "Broadcom Thor Ultra Ethernet NIC at Hot Chips 2026,"
  https://www.servethehome.com/broadcom-thor-ultra-ethernet-nic-at-hot-chips-2026/, accessed 2026-09-05.
- [S12] StorageReview, "Broadcom Thor Ultra: UEC-Compliant 800G AI Ethernet NIC for
  100K+ XPU Scale-Out," https://www.storagereview.com/news/broadcom-thor-ultra-uec-compliant-800g-ai-ethernet-nic-for-100k-xpu-scale-out, accessed 2026-09-05.
- [S13] NVIDIA Developer Forums, "Selective repeat does not seem to work on CX-7 NICs even
  enabled in mlxconfig," https://forums.developer.nvidia.com/t/selective-repeat-does-not-seem-to-work-on-cx-7-nics-even-enabled-in-mlxconfig/361958, accessed 2026-09-05.
- [S14] NVIDIA Developer Forums, "ConnectX-7 RoCEv2 RC QP out-of-order receive behavior
  with non-NVIDIA packet-spraying switches," https://forums.developer.nvidia.com/t/connectx-7-rocev2-rc-qp-out-of-order-receive-behavior-with-non-nvidia-packet-spraying-switches/372654, accessed 2026-09-05.
- [S15] "Datacenter Ethernet and RDMA: Issues at Hyperscale," arXiv:2302.03337,
  https://arxiv.org/pdf/2302.03337, accessed 2026-09-05 (go-back-N-by-default framing).
- [S16] SRNIC (USENIX NSDI), selective-repeat hardware architecture summary: see search
  results; exact URL not individually re-fetched, cited via search summary only. **Treat
  as lower-confidence than directly fetched sources.**
- [S17] Flor, OSDI'23, "Flor: An Open High Performance RDMA Framework,"
  https://www.usenix.org/system/files/osdi23-li-qiang.pdf, accessed 2026-09-05 (title/claim
  summary only, not deep-read).

Repository files (read-only, for Part 2):
- `/config/repositories/astra-sim/docs/agents/loss-tolerant-rdma-decision.md`
- `/config/repositories/astra-sim/docs/agents/loss-tolerant-rdma-audit.md`
- `/config/repositories/astra-sim/experiments/ring_3d/GLOSSARY.md`
- `/config/repositories/astra-sim/extern/network_backend/ns-3/src/point-to-point/model/rdma-hw.cc`
- `/config/repositories/astra-sim/extern/network_backend/ns-3/src/point-to-point/model/rdma-queue-pair.h`
- `/config/repositories/astra-sim/extern/network_backend/ns-3/src/point-to-point/model/rdma-queue-pair.cc`
- `/config/repositories/astra-sim/extern/network_backend/ns-3/scratch/common.h`
- `/config/repositories/astra-sim/experiments/ring_3d/generate.py`
- `/config/repositories/astra-sim/extern/network_backend/ns-3/src/point-to-point/model/switch-node.cc`
- `/config/repositories/astra-sim/extern/network_backend/ns-3/src/point-to-point/model/rdma-hw.h`

## Unverified list (explicit)

- Whether any UEC member or third party has published a public **ns-3** UET module:
  none found; this is a negative result, not a proof of nonexistence.
- Exact quantitative numbers from STrack [S5] and REPS [S8] beyond their titles/abstracts:
  not deep-read.
- A single authoritative primary source for "DCQCN's known weaknesses (slow convergence,
  PFC dependence)" as a standalone claim: the NSCC spec's own contrast text [S3 p.365]
  is the strongest primary source found; broader DCQCN critique literature exists but was
  not individually pinned to a citation here.
- Whether NVIDIA Spectrum-X / ConnectX-8 implements UEC-conformant packet trimming
  specifically, versus NVIDIA's own separate adaptive-routing/telemetry mechanisms.
- The exact defensible multiplier to rescale `RATE_AI`/`RATE_HAI`/`MIN_RATE` for a
  400 Gb/s link in this codebase: no UEC or vendor-published value was found; the
  "scale like KMIN_MAP/KMAX_MAP" heuristic in Part 3(a) is an inference, not a sourced
  number, and should be validated empirically before being treated as calibrated.
- Any external, apples-to-apples number for "cost of a lost packet on a UEC fabric" in the
  same units as our canary (`W`, absolute FCT ms): none found; see Part 1 §5 and Part 3(c).
- SRNIC's exact venue/URL [S16]: cited from a search-result summary rather than a directly
  fetched primary document; treat with lower confidence than other citations here.
