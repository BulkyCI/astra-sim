# Literature review: DCQCN as the congestion control on a lossy, trimming RDMA fabric

## For the paper

Each pair gives (a) a definition and (b) a justification. Citation numbers
refer to the list at the end of this file.

Pair 1, which puts deployment and independence first:

> (a) DCQCN is a rate-based, end-to-end congestion control for RoCEv2:
> switches mark packets with ECN, the receiver returns congestion
> notification packets, and the sender NIC cuts its rate [1].
> (b) DCQCN runs without priority flow control once the NIC repairs losses
> selectively [2]. It is the default congestion control of Mellanox RoCEv2
> NICs [4], and the ns-3 RDMA model implements it [5]. FORGIVE decides
> which congestion signals reach the sender, so the rate controller that
> consumes them is interchangeable.

Pair 2, which states the successor openly:

> (a) DCQCN [1] is the ECN-driven rate control that ships in RoCEv2 NICs;
> it was designed for a lossless fabric protected by priority flow control.
> (b) Ultra Ethernet specifies a window-based controller, NSCC, that
> reacts to ECN, delay, and trimmed packets [18], [19], and one hyperscaler
> has retired DCQCN [15]. We keep DCQCN because it is the default of
> Mellanox RoCEv2 NICs [4], the ns-3 RDMA model implements it [5], and
> selective repair lets it run without priority flow control [2].

No included paper supports the last sentence of pair 1. It is a claim about
FORGIVE's own design, and it holds only if the implementation gates a
signal that NSCC also consumes (ECN echoes or trims), not only DCQCN's CNPs.

## Summary

As of 29 September 2026, the corpus treats DCQCN as the incumbent that
trimming fabrics replace, and it holds no evaluation of DCQCN on a trimming
fabric. DCQCN was built for PFC-protected, go-back-N RoCEv2; one 2018
simulation study ran it without PFC once the NIC repaired losses
selectively. Ultra Ethernet specifies NSCC and RCCC and never mentions
DCQCN. Meta runs 400G without DCQCN, and Alibaba's newest RNIC uses an
in-house window controller. Three common assumptions fail: the MRC paper
names no congestion control, Alibaba HPN never mentions DCQCN, and Stellar
does not use it. A DCQCN baseline in a 2026 simulation paper rests on NIC
prevalence, availability in the ns-3 RDMA model, and a mechanism that does
not depend on the rate law.

## Method

The review ran 27 logged searches on 29 September 2026 (24 OpenAlex, 2
arXiv, 1 Crossref); 20 were truncated ranked samples. They fetched 251
records, 148 unique; 128 were excluded at title and abstract and 20
included, above the lite band of 5 to 10. Fourteen were read in full text
and six at abstract level ([3], [4], [6], [7], [13], [14]) because the ACM
Digital Library returned HTTP 403 and no preprint was found. For [2] the
arXiv extended version was read, and for [20] the latest arXiv version.
All 18 DOIs resolve; the 14 Crossref DOIs match their titles, and the four
arXiv DOIs and two arXiv identifiers match the titles in the fetched PDFs.

## What DCQCN is and where it runs

DCQCN is "a rate-based, end-to-end congestion protocol" built on QCN and
DCTCP and implemented mostly in the NIC: switches mark with ECN, the
receiver sends CNPs, the sender cuts its rate (full text) [1]. Its first
design requirement is to "function over lossless, L3 routed" networks, and
with PFC disabled its tenth-percentile incast throughput is zero [1].
Hoefler et al. call RoCE's rate control "intimately linked to the lossless
transport assumption" (full text) [10].

Independent groups call DCQCN the default: Microsoft deployed it [1], it
was Alibaba's default in 2019 [12], and Meta [15] and STrack [8] call it de
facto (full text); Chameleon names it the default of Mellanox RoCEv2 NICs
(abstract) [4]. Later production reports move away from it. Meta's 200G
tuning bought about 3 % completion time for 2 to 3 times more PFC; at 400G
Meta runs PFC only, with receiver-driven admission in the collective
library (full text, p. 9) [15]. That fabric is lossless, not trimming.
Stellar's RNIC runs "an in-house, window-based" controller on ECN and RTT
(full text, p. 9) [16]; HPN names no congestion control [17]. MRC reports
that DCQCN tuning is traffic-pattern specific and cites Meta's decision to
disable it (full text, p. 12) [9].

## What Ultra Ethernet and MRC specify

UET offers NSCC, a sender window controller "available on each UE NIC",
and RCCC, a receiver-credit controller "optional to implement"; either can
be disabled at runtime (full text, p. 16) [19]. NSCC combines egress ECN
with RTT in four cases and applies QuickAdapt on trims or losses; switches
need only ECMP and egress ECN, and trimming is optional [19]. The UET paper
never mentions DCQCN and describes no ECN-only rate mode. SMaRTT, the basis
of NSCC, targets lossy networks (full text) [18].

MRC extends RoCEv2 RC with spraying, SACK-based selective retransmission,
trimming, and PFC disabled; it turns ECN off on the last hop and uses ECN
for load balancing (full text, p. 3) [9]. It does not name the algorithm
that sets its rate or window.

## Evidence on DCQCN with selective repair

One study tests this directly. IRN's loss recovery is "orthogonal" to
DCQCN and Timely (full text, p. 3) [2]; with DCQCN and no PFC, IRN beats
RoCE with PFC, and enabling PFC changes IRN+DCQCN by at most +5 % or −20 %
[2]. IRN models drops, not trims.

SMaRTT [18], STrack [8], and MRC [9] compare against RoCEv2 with DCQCN, but
that baseline also carries PFC, single-path ECMP, and go-back-N (full
text). SMaRTT attributes RoCE's 3 to 5 times slowdown to "DCQCN
overreaction and ECMP collisions" and adds that finer tuning makes RoCEv2
near-optimal on the tested incast at the cost of other patterns [18]. None
isolates DCQCN on a trimming fabric. On a PFC fabric in ASTRA-sim over
ns-3, DCQCN, DCTCP, TIMELY, and HPCC had "little impact" on training time
compared with PFC alone (full text) [5]. The congestion control behind DCP
[6] and the trimmed-gradient work [14] is unknown at abstract level.

## Why the baseline remains defensible

The ns-3 simulator integrated with ASTRA-sim implements DCQCN, TIMELY,
DCTCP, and HPCC (full text, p. 4) [5], and HPCC's ns-3 evaluation runs
DCQCN [12]. Lossy-fabric mechanisms are specified independently of the
controller above them: IRN's loss recovery [2], and REPS, which works "with
any CC algorithm" that accepts out-of-order packets (full text, p. 3)
[20]. DCQCN is thus a defensible baseline for a mechanism that sits beside
the congestion control; it is not a stand-in for what a UET fabric runs.

## Limitations of this review

Six papers were read at abstract level. The review reached the UET design
paper [19] but not the specification text. It ran one search round without
snowballing, on ranked samples.

## Gaps and open questions

None of the 20 included papers evaluates DCQCN with packet trimming and
selective retransmission. None reports a public ns-3 model of NSCC or RCCC:
SMaRTT used htsim [18], and UET says only "simulation" [19]. None states
that MRC uses NSCC.

## Included papers

| [n] | title | year | venue | read level | key |
| --- | --- | --- | --- | --- | --- |
| 1 | Congestion Control for Large-Scale RDMA Deployments | 2015 | SIGCOMM | full-text | doi:10.1145/2785956.2787484 |
| 2 | Revisiting network support for RDMA | 2018 | SIGCOMM | full-text | doi:10.1145/3230543.3230557 |
| 3 | DCQCN+: Taming Large-Scale Incast Congestion in RDMA over Ethernet Networks | 2018 | ICNP | abstract | doi:10.1109/icnp.2018.00021 |
| 4 | Poster: Chameleon: Automatic and Adaptive Tuning for DCQCN Parameters in RDMA Networks | 2023 | SIGCOMM poster | abstract | doi:10.1145/3603269.3610865 |
| 5 | Impact of RoCE Congestion Control Policies on Distributed Training of DNNs | 2022 | HotI | full-text | doi:10.1109/hoti55740.2022.00021 |
| 6 | Revisiting RDMA Reliability for Lossy Fabrics | 2025 | SIGCOMM | abstract | doi:10.1145/3718958.3750480 |
| 7 | Falcon: A Reliable, Low Latency Hardware Transport | 2025 | SIGCOMM | abstract | doi:10.1145/3718958.3754353 |
| 8 | STrack: A Reliable Multipath Transport for AI/ML Clusters | 2024 | arXiv | full-text | doi:10.48550/arxiv.2407.15266 |
| 9 | Resilient AI Supercomputer Networking using MRC and SRv6 | 2026 | arXiv | full-text | doi:10.48550/arxiv.2605.04333 |
| 10 | Datacenter Ethernet and RDMA: Issues at Hyperscale | 2023 | arXiv | full-text | doi:10.48550/arxiv.2302.03337 |
| 11 | Implementing packet trimming support in hardware | 2022 | arXiv | full-text | doi:10.48550/arxiv.2207.04967 |
| 12 | HPCC: High Precision Congestion Control | 2019 | SIGCOMM | full-text | doi:10.1145/3341302.3342085 |
| 13 | Re-architecting datacenter networks and stacks for low latency and high performance | 2017 | SIGCOMM | abstract | doi:10.1145/3098822.3098825 |
| 14 | When ML Training Cuts Through Congestion: Just-in-Time Gradient Compression via Packet Trimming | 2024 | HotNets | abstract | doi:10.1145/3696348.3696880 |
| 15 | RDMA over Ethernet for Distributed Training at Meta Scale | 2024 | SIGCOMM | full-text | doi:10.1145/3651890.3672233 |
| 16 | Alibaba Stellar: A New Generation RDMA Network for Cloud AI | 2025 | SIGCOMM | full-text | doi:10.1145/3718958.3750539 |
| 17 | Alibaba HPN: A Data Center Network for Large Language Model Training | 2024 | SIGCOMM | full-text | doi:10.1145/3651890.3672265 |
| 18 | SMaRTT: Sender-based Marked Rapidly-adapting Trimmed & Timed Transport | 2024 | arXiv | full-text | arXiv:2404.01630 |
| 19 | Ultra Ethernet's Design Principles and Architectural Innovations | 2025 | arXiv | full-text | arXiv:2508.08906 |
| 20 | REPS: Recycled Entropy Packet Spraying for Adaptive Load Balancing and Failure Mitigation | 2024 | EuroSys 2026 (arXiv 2407.21625 read) | full-text | doi:10.1145/3767295.3769320 |

Papers [3], [7], [11], and [13] carry no claim in the text; [13] and [11]
are the origin and the hardware feasibility of trimming.
