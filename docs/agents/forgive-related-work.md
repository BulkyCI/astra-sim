# Forgive protocol: what the literature already has

Four scoping reviews run on 2026-09-08 with the lit-review tool (OpenAlex,
arXiv, Crossref; criteria fixed before search; every citation below is a
retrieved record), plus three papers read directly because the reviews'
handoffs pointed at them. Session directories and full reports are under
the session scratchpad `litrev/{A,B,C,D}/report.md`. Read level is
stated per paper: full means the full text was read, abstract means the
abstract only.

| review | question | records | included | full text |
| --- | --- | ---: | ---: | ---: |
| A | deliberate gradient loss in the communication layer | 139 | 9 | 7 |
| B | trimming and receiver-driven transports, partial reliability | 628 | 12 | 4 |
| C | congestion-control bypass under a budget; DCQCN penalty and tuning | 535 | 37 | 0 |
| D | phase-dependent tolerance to gradient loss or compression | 353 | 30 | 2 |

## 1. The short answer

Receiver-side bounded loss for gradient traffic is documented. The
composition we built is not.

Known, with the paper that owns it:

- A receiver that stops asking for retransmission once enough of a tensor
  has arrived, with the tolerated fraction fixed per model: MLT (Wang et
  al., NSDI 2024, full). Its precursor DLCP (Wang et al. 2020, arXiv
  2008.08445, full by review A).
- A receiver that closes a round early and adapts the tolerated fraction
  to network conditions: LTP (Chen et al. 2023, arXiv 2305.04279,
  abstract and introduction).
- A round bounded by an adaptive timeout, with loss made harmless by a
  Hadamard mixing of the gradient: OptiReduce (Warraich et al., NSDI
  2025, full by review A).
- Packets laid out so that a trimmed packet is a compressed gradient and
  is never retransmitted: trimmable gradients (Chen, Vargaftik, Ben
  Basat, HotNets 2024, full).
- Loss tolerated at LLM scale by an unbiased estimator with bounded
  parameter drift, 10 to 40 % i.i.d. loss on Llama 2 7B: Weintraub,
  Banner, Orda 2025 (arXiv 2507.07114, full by review A).
- A tolerated fraction that changes with the training phase: DBLP (Ma et
  al. 2026, arXiv 2605.01989, full by review A), building on Accordion
  (Agarwal et al., MLSys 2021, full by review D) and critical learning
  periods (Achille, Rovere, Soatto, ICLR 2019, full by review D).
- Partial reliability declared by the application before data flows:
  PR-SCTP (RFC 3758, full by review B), QUIC DATAGRAM (RFC 9221, full by
  review B), Ultra Ethernet's unreliable delivery mode (Hoefler et al.
  2025, arXiv 2508.08906, full by review B).
- Flows that are allowed a weaker congestion response by class: deadline
  flows in D3, D2TCP, PDQ and Karuna; line rate by default in pFabric;
  real-time media in GCC, NADA, SCReAM and GRACE (all abstract, review
  C). The harm of flows that do not respond at all: Floyd and Fall 1999
  (abstract, review C).

Not found, with the null searches that establish it:

- A receiver that decides per trimmed range, as the switch reports it,
  whether to request or forgive that range, on a selective-retransmission
  fabric (review B, gap over 13 queries; review A saturation round on
  forgiveness and trimming vocabulary, 4 queries).
- A loss budget kept per receiving rank per training step, charged by
  both sender-side suppression and receiver-side forgiveness, that closes
  when the step's all-reduce completes (no record in A or D expresses
  tolerance in bytes lost per step; D probes s1 to s7).
- An RDMA flow that ignores DCQCN's congestion notifications under a
  receiver-side loss budget and is put back under congestion control by
  the receiver's first refusal (review C, probe s51).
- A measurement of DCQCN's time penalty at 200 or 400 Gbps, or a
  head-to-head study separating DCQCN's inherent cost from mistuned
  defaults (review C, probes s50, s52, s54).
- Phase-gated gradient loss or compression at transformer or LLM scale
  (review D, probes s9, s10, s19, s20, s22, s26).

## 2. The nearest prior work, read in full

### MLT, Wang et al., NSDI 2024

Mechanism. Before training, sender and receiver agree on a tolerated loss
fraction p per tensor. The receiver counts delivered bytes. When they
reach (1 minus p) of the tensor, it sends a stop signal over a reliable
channel and the sender stops. If the sender finishes first, it probes,
the receiver answers with a bitmap of received packets, and the sender
retransmits what is missing until the stop arrives. Lost gradients are
filled with zero at the receiver. Switches do priority queueing and
selective dropping by layer and by gradient magnitude, using DSCP and ECN
fields on commodity hardware. Rate control is a minimal TIMELY-like
delay-based algorithm; the paper says that "in virtue of the
loss-tolerance feature, MLT only requires a minimal rate control to avoid
congestion collapse".

Evidence. Tolerated fractions with the same number of training rounds
and the same accuracy: 0.7 to 3.3 % across sixteen CNN and RNN models on
ImageNet-100 and WikiText-2 (their Table 1). With a quality target and
more rounds allowed, 10 %. At 20 and 30 % more epochs are needed. Their
evaluation sets the bound to 10 %. Testbed of 8 GPU servers on 100 Gbps
with Mellanox SN2100 switches, plus ns-3 simulation; up to 62 % shorter
training time than prior work, and lower tail flow completion than DCTCP,
PIAS, pFabric and NDP.

What it does not have. The decision is one stop per tensor, taken at the
end, so the bytes that are lost are whichever arrive last. Nothing is
decided per range at the time the network rejects it. The bound is per
model and constant over training. Congestion control is weakened
globally for every flow, not per flow under a budget, and there is no
re-arm. The transport is UDP in user space; the authors state that RDMA
NICs cannot host it.

### Trimmable gradients, Chen, Vargaftik, Ben Basat, HotNets 2024

Mechanism. The sender splits each gradient coordinate into a 1-bit head
and a 31-bit tail and packs all heads at the front of the packet. A
congested switch trims the packet to 87 bytes and forwards it. The
receiver decodes the heads as a quantized gradient and never requests
retransmission. Loss is therefore compression, chosen by the switch, with
no bound: every trimmed packet is accepted as is.

Evidence. Two servers, 100 Gbps, VGG-19 on CIFAR-100, trimming simulated
by random selection. Stochastic quantization tolerates 10 to 20 % of
packets trimmed with no rise in time to accuracy; the Randomized Hadamard
Transform variant reaches baseline accuracy at 50 %. Unmodified NCCL
tolerates 0.15 to 0.25 % packet drops before disproportionate slowdown.

What it does not have. No budget, no phase, no receiver verdict, no
protection of critical steps, and no congestion-control interaction: the
paper's own future-work section asks for a congestion control that
"slightly under-compress[es] and over-send[s] so that the gradient
traffic always saturates the link" and lets the switch trim the excess.
That is what the exemption in our protocol does, with a budget that
paper does not have.

### LTP, Chen et al. 2023

Parameter-server setting, 8 workers. Out-of-order transmission and
acknowledgements so a lost packet does not block delivery. An Early
Close mechanism adjusts the tolerated loss threshold to network
conditions, and bubble filling substitutes missing data. Congestion
control is a bandwidth-delay-product estimator in the style of BBR,
chosen to ignore non-congestive loss. Reported up to 30x throughput over
TCP with no accuracy loss. Abstract and introduction read; the
threshold rule was not extracted.

## 3. Where our protocol stands

| element | MLT | trimmable gradients | OptiReduce | ours |
| --- | --- | --- | --- | --- |
| who decides recovery | receiver, once per tensor at the end | switch, per packet, no recovery | receiver, per round, by timeout | receiver, per trimmed range, as reported |
| what bounds the loss | fraction per model, constant | nothing | round deadline | bytes per (rank, step), phase-dependent |
| which bytes are lost | the last to arrive | whatever the switch trimmed | whatever is late | whatever the switch trimmed, up to the budget |
| critical steps | same bound as any step | none | none | tight bound |
| congestion control | minimal, global | future work | untouched | full DCQCN; budgeted flows exempt until refused |
| transport | UDP, user space | UDP, planned | UDP | RDMA-style, trimming, selective retransmission |
| evidence | 8 servers at 100 Gbps, ns-3 | 2 servers, simulated trimming | up to 144 nodes, cloud | ns-3, 64 ranks, 400 Gbps |

Our design adds three elements that no row of that table has.

1. Per-range forgiveness driven by the switch's own trim report on a
   selective-retransmission transport. MLT loses the tail of a transfer;
   we lose what the fabric rejected, charged as it happens, and the rest
   is still recovered by the ordinary retransmission path.
2. A budget per receiving rank and training step, spent by both
   sender-side suppression and receiver-side forgiveness, with the
   critical steps held tight. DBLP moved MLT's bound across phases; the
   ledger moves it to the granularity the tolerance claim is made at.
3. A congestion-control exemption that is per flow, budget-bounded and
   self-revoking: the receiver reports that forgiving every byte it is
   missing would exceed the step's tolerance, and that report puts the
   flow back under DCQCN until a later report says otherwise. MLT weakened congestion control
   for every flow because loss was tolerated; the deadline-aware
   controllers scale the response by class and never revoke it; nothing
   in review C exempts an RDMA flow from DCQCN's own signal under a loss
   budget.

And two findings that reframe the prior work on a modern fabric:

4. On a trimming fabric with selective retransmission, the tail that MLT,
   LTP and OptiReduce cut does not exist. Run #120 measured the congestion
   episode at under 1 % of training time at every point of a 2x2x2 map.
   Those systems faced TCP or UDP with millisecond retransmission
   timeouts; the fabric already removed that cost.
5. What remains to buy back on such a fabric is the congestion-control
   reaction, 18 to 24 % of training time under DCQCN. At budget 0.1 the
   protocol recovers 16.1 to 16.7 % of training time (run #127), of which
   forgiveness under the controller supplies 5.5 to 6.6 % (run #126); the
   exemption roughly doubles what forgiveness alone gains.

## 4. What the reviews say about our assumptions

- Tolerance. MLT's profiled bounds are 0.7 to 3.3 % of gradient bytes at
  equal rounds and 10 % at a quality target, on CNNs and RNNs. Weintraub
  2025 shows Llama 2 7B at 10 % i.i.d. loss with 1.17 % worse perplexity
  and at 40 % with 6.65 % worse. DBLP's 40 % is its own DenseNet result.
  Our exempt run at budget 0.4 lost 21.3 to 21.8 % of data-parallel
  bytes, inside what Weintraub measured and above what MLT profiled; at
  budget 0.1 under the design of record it loses 7.55 to 7.57 %, and with
  Bernoulli pacing at 0.25 it loses 5.5 to 5.6 % for the same time. No
  paper gates loss by training phase at LLM scale, and none measures loss
  that is bursty or correlated, which is what a trimming fabric
  produces.
- DCQCN. Chameleon (SIGCOMM 2023 poster) reports that more than ten
  DCQCN parameters have non-negligible effect on AI-training traffic;
  ECN-or-Delay (CoNEXT 2016) shows DCQCN's stability is non-monotonic in
  its rate constants; DCQCN+ (ICNP 2018) targets the rate-increase timer
  at incast scale; RoCC (TPDS 2023) reports 1.7 to 7x lower tail latency
  than DCQCN from self-tuning gains. No paper measures DCQCN at 400 Gbps
  and none separates inherent cost from mistuned defaults. The tuning
  sweep planned as phase 1 has no substitute in the literature, and the
  claim must say "DCQCN as configured" until it runs.
- Fairness. Floyd and Fall's result on unresponsive flows is the
  objection a reviewer will raise. The exemption is bounded by the budget
  and ended by the receiver's report, which is more than an unresponsive
  flow has, and less than a proof. The two-tenant experiment (phase 5) is
  the answer.
- Currency of the setting. Meta runs its 400 Gbps training fabric with
  DCQCN off (Gangidi et al., SIGCOMM 2024, abstract). Where there is no
  congestion control, the exemption has nothing to act on and only
  finding 4 above applies.

## 5. Sources read directly

- Chen, Vargaftik, Ben Basat. When ML Training Cuts Through Congestion:
  Just-in-Time Gradient Compression via Packet Trimming. HotNets 2024.
  doi:10.1145/3696348.3696880. Full text, from the conference PDF.
- Wang, Tian, Chen, Wan, Xia, Zeng, Bai, Jiang, Wang, Chen. Towards
  Domain-Specific Network Transport for Distributed DNN Training. NSDI
  2024. Full text, from the USENIX PDF.
- Chen, Shi, Liu, Ai, Liu, Xu. Boosting Distributed Machine Learning
  Training Through Loss-tolerant Transmission Protocol. 2023, arXiv
  2305.04279. Abstract and introduction.
