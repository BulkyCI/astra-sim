<!-- Source: NDP read from https://s.joefang.org/ndp.pdf, SIGCOMM 2017, pp. 29-42; EQDS, SMaRTT-REPS, MRC papers, UEC v1.0.3; read 2026-09-05. -->

# NDP to UET and MRC: lineage of receiver-driven loss handling

UEC facts below are sourced to UE Specification v1.0.3 page numbers, the same
source as [uec-transport-brief.md](uec-transport-brief.md), which is cited
directly where it already establishes a fact.

## Part 1: NDP in full

**Problem statement.** NDP targets request/response traffic where "the big
problem today is latency" (p.29). Lossless Ethernet is low-delay at light load,
but "based on experience deploying RoCEv2 at Microsoft... a lossless network does
not guarantee low latency. When congestion occurs, queues build up and PFC pause
frames are generated," and pausing "causes collateral damage to other flows
traversing the same incoming port destined for different output ports" (p.29-30).
TCP/DCTCP fail differently: "with short flows, tail loss is common, and then you
have to fall back on retransmission timeouts (RTO). Short RTOs are only safe if
you can constrain the delay in the network," and loss "couples badly with
per-packet multipath forwarding" since out-of-order arrival defeats fast
retransmit (p.30). Switch buffer size is the fulcrum: large buffers cut loss but
add queuing delay; NDP commits to small buffers (eight packets), pushing
overflow cost onto a cheap, fast repair path.

**The four mechanisms.** (a) *Per-packet multipath spraying*: "the only solution
here is to stripe across multiple paths on a per-packet basis" (p.30), sender-
chosen because "senders choose the paths, they can do a better job of load
balancing than if the switches randomly choose paths" (p.31); reordering is
accepted, not an error: "the basic protocol design is robust to reordering, as it
does not need to make inference about loss from other packets' sequence numbers"
(p.33). (b) *Packet trimming*: switches keep "two queues: a lower priority queue
for data packets and a higher priority queue for trimmed headers, ACKs and
NACKs," so "arriving trimmed headers tell the receiver exactly what the demand
is" (p.32). Trimming makes loss cheap: "Due to packet trimming, it is very rare
for a packet to be actually lost... the sender can know very quickly if a packet
was actually lost" (p.33). (c) *Receiver-driven pull congestion control*: "After
sending a full window of data at line rate, NDP senders stop sending. From then
on, the protocol is receiver-driven. An NDP receiver requests packets from the
senders, pacing the sending of those requests so that the data packets they
elicit arrive at a rate that matches the receiver's link speed" (p.33), via a
single shared "pull queue" per receiver (p.33). First-RTT sending is
unconstrained: "to minimize delay we must be optimistic and assume there will be
enough capacity to send a full window of data in the first RTT... a full window
is likely to be only about 12 packets" (p.32); sensitivity analysis later finds
~20-30 packets needed for full utilization (p.38). The rationale for receiver
control: "the receiver has a complete view of what is happening... deliberate
unfairness is possible, because the receiver knows its own priorities" (p.34),
and "the receiver is the only entity that can dynamically prioritize its inbound
traffic, and this impacts protocol design" (p.30). (d) *State machine*: NACK on a
trimmed header ("prepare the packet for retransmission (but not yet send it)"),
ACK on full receipt, PULL to release data, and RTO nearly unused: "senders rarely
need to rely on the RTO, so collapse due to unnecessary retransmissions is not
possible" (p.35); "the maximum RTO could safely be as low as 1ms" given a 400
microsecond worst-case RTT (p.34).

**Incast.** NDP claims "greater than 95% of the maximum network capacity... with
switch queues of only eight packets" and "near-perfect delay and fairness in
incast scenarios" (p.29). "All competing flows start with the same window...
Receiver fairness is achieved by using a fair queuing scheme for packets in the
pull-queue" (p.34). An optional "return-to-sender" bounces a trimmed header's
loss notice straight back when even the header queue overflows, used "only if it
is not expecting more PULLs" to avoid echoing the incast (p.34). At an 8000-flow
incast, "the mean number of retransmissions barely exceeds one" (p.40).

**Results.** RPC latency: NDP median 62 microseconds versus TCP Fast Open's 4x
and TCP's 5x (p.37). Seven-to-one incast: "within 5% of the theoretical optimal
completion time... four times faster" than TCP (p.37). Permutation traffic,
432-node FatTree: NDP 92% utilization versus DCTCP/DCQCN's ~40% and MPTCP's
89%, slowest NDP flow still at 9Gb/s (p.38). Short-flow tail FCT "four times
lower at the 99%" than DCTCP, ten times better than MPTCP (p.38). At 4:1
oversubscription with 70% of packets trimmed at the ToR, "NDP performs
robustly, providing slightly better performance than DCTCP" (p.40-41).
Implemented in Linux/DPDK, a software switch, NetFPGA SUME hardware ("the
complexity added by NDP is small," p.36), and P4 (p.36).

**Limitations stated by the authors.** NDP "will behave poorly" on asymmetric
topologies (BCube, Jellyfish); reconciling per-path congestion control with
pull-based receiver control "remains an open question" (p.36). On persistently
oversubscribed cores "some form of congestion control would be useful to reduce
server retransmission load," though NDP still beats DCTCP without one (p.36,
p.40). NDP "may shut out competing TCP traffic" absent fair queuing between
separate queues (p.36). The implementation is "moderately expensive in terms of
CPU resources... because of the need for accurate pacing of PULLs" (p.42).
Security is addressed only via first-RTT connection-ID/time-wait state; encryption
and cross-datacenter operation are not discussed at all.

## Part 2: lineage to UET and MRC

**Trimming.** NDP forwards trimmed headers at strict priority, 10:1 weighted
round robin against data (p.32). UET section 4.1 keeps forward-to-destination
trimming but caps bandwidth share instead of strict priority: "WDRR with 25% of
the bandwidth allocated to trimmed packets is also a good configuration option,
at the expense of moderate trimmed packet loss in large incasts" (UEC v1.0.3
p.463, established in `uec-transport-brief.md`). UET also makes explicit what
NDP left open: "This specification focuses only on sending the trimmed packet to
the destination... back to the source... is not part of this specification"
(UEC v1.0.3 p.459), whereas NDP itself specifies return-to-sender as a
first-class incast optimization. MRC describes the mechanism almost verbatim:
"a packet that would have been dropped due to congestion has its payload
trimmed off and is priority-forwarded to the destination. The receiving NIC then
generates a NACK to trigger fast retransmission" (MRC/OpenAI paper, extraction
p.3), and adds that trimming "also lets MRC distinguish congestion loss from
other packet loss, which in AI clusters is mostly due to link flaps and
failures" (same) - a cause discriminator NDP does not make.

**Receiver-driven pull CC.** NDP's pull queue is EQDS's direct ancestor: "Its
receiver-driven control loop is loosely based on NDP... this allows a burst of
packets to be sent in the first RTT before credit-based control from the
receiver takes over" (EQDS, extraction p.4); "as with NDP, the receiving EQIF
sends PULL packets containing credit to the sending EQIF" (p.5). UET's RCCC
descends from EQDS directly: "The UET receiver-credit congestion control (RCCC)
service is derived from EQDS... RCCC uses end-to-end credit control messages
('pull messages') sent by the destination at a defined 'rate' to all concurrent
sources" (UEC v1.0.3 pp.399-400). But the receiver line does not own UET's default
CC: NSCC is sender-based and window-based, and the spec argues this is required
for lossy fabrics versus rate-based DCQCN (quoted at length in
`uec-transport-brief.md`, UEC v1.0.3 p.365). SMaRTT-REPS, cited by the spec as
NSCC's source, states this plainly: it "inspired the implementation of Network
Signal Congestion Control (NSCC), the standard sender-based congestion control
algorithm... We provide the crucial design rationale... for the standard's
sender-based congestion control" (extraction p.1). Its reasoning: "vanilla
EQDS, although more fair, does not manage fabric congestion as effectively as
sender-based CC algorithms," since receiver-only control has "limited visibility
of congestion happening in the network fabric" beyond the last hop (p.2), and
"receiver-based algorithms... require extra control packets and data structures
(e.g., pull queues) on the receiver side," while "sender-based schemes do not
require such extra complexity" (p.3-4) - a fabric-visibility and NIC-memory
argument, not a PCIe-specific one; no PCIe text was found anywhere searched. UET keeps both:
NSCC default, RCCC optional for incast specifically (UEC v1.0.3 pp.399-400). MRC goes
further and drops receiver credit entirely: its CC is "designed... with focus on
NSCC... a sender-based window-driven algorithm" (MRC transport paper, extraction
p.3), and neither MRC paper mentions EQDS, RCCC, or "credit" as a rate-control
mechanism (confirmed by full-text search of both). MRC's section titled
"Receiver-Driven Bounded In-Flight Transmission" is a false cognate: it
describes Maximum PSN Range (MPR), a responder-advertised window bounding *how
many packets can be outstanding*, negotiated at connection setup and optionally
SACK-updated (p.3) - a flow-control window, not a per-RTT pacing/credit
mechanism. The pull lineage survives intact only NDP to EQDS to RCCC; UET keeps
it as an optional incast sibling to sender NSCC; MRC drops it.

**Spraying and reordering.** NDP's sender-permuted path list (p.31) becomes
UET's entropy pool of 64-256 values with per-path ECN/trim feedback and RUD
out-of-order placement (`uec-transport-brief.md`). MRC sprays per packet via an
Entropy Value field (MRC transport paper, p.2) but production deployment
disables switch adaptive routing "because we didn't want two adaptive routing
mechanisms interacting with each other," using static SRv6 source routing while
MRC's own EV state machine (GOOD/SKIP/DENIED/ASSUMED_BAD) does end-to-end
avoidance (MRC/OpenAI paper, p.2), converging independently with NDP's own
path scoreboard and path-penalty mechanism (p.34): the endpoint tracks path
health, not the network.

**First-RTT unconstrained sending.** NDP: send "a full window of data in the
first RTT... without probing" (p.32). UET's NSCC reasons identically and
concludes "new flows should, by default, start at line rate, using a window
around MaxWnd" (UEC v1.0.3 p.365-366), noting "the sender- and receiver-driven
approaches behave similarly in the first RTT, starting at line rate by default"
(p.366). RCCC mirrors this: a source "can start at line rate by sending up to a
BDP of 'speculative packets'" (UEC v1.0.3 pp.399-400). Neither MRC paper states an explicit
initial-window policy; unverified rather than contradicted.

**Loss as a signal.** NDP: a trim is a clean congestion signal, true loss is
rare corruption (p.33, 35). UET keeps trimming as repair trigger and congestion
signal but excludes last-hop trims from NSCC "when RCCC is also enabled, because
RCCC can handle last-hop congestion by itself" (UEC v1.0.3 p.356). MRC adds a
use NDP and UET lack, a path-quality signal: untrimmed loss means path failure,
not congestion: "When a packet is not trimmed but actually lost, MRC assumes the
path has failed and immediately stops using the corresponding EV" (MRC/OpenAI
paper, p.3).

**No-RTO philosophy.** NDP wants RTO to almost never fire. UET keeps it as an
explicit "MUST" backstop with exponential backoff (`uec-transport-brief.md`, UEC
v1.0.3 p.290-297). MRC lists "Linear + Exponential ACK timeout" as mandatory
(Table I, p.2) and frames trimming as what avoids that timer: trimming "enables
fast retransmissions that bypass retransmit-timeout timers" (p.3). All three
converge on NDP's stance: RTO exists but a healthy network rarely uses it.

**People.** Handley and Raiciu are NDP's first two authors (p.1) and reappear on
EQDS (p.2), on SMaRTT-REPS's author list per the spec's own citation
("Bonato, Kabbani, De Sensi, Pan, Le, Raiciu, Handley, Hoefler,"
`uec-transport-brief.md` S4), and on both MRC papers (Handley as OpenAI and
corresponding author; Raiciu as Broadcom co-author on both). Olteanu is EQDS's
first author. The same researchers carried receiver-pull from NDP through EQDS
into the UEC spec while co-authoring the sender-based SMaRTT-REPS/NSCC line and
the MRC papers choosing NSCC alone: they built, then deliberately bounded, the
receiver-driven mechanism once fabric-wide congestion and NIC-memory
constraints were taken seriously.

## Part 3: implications for a bounded-loss gradient transport

**Cost of a lost packet in NDP.** A trimmed header at high priority, one
immediate NACK, one PULL added to the shared pull queue, one retransmission
carried by that PULL, an ACK on receipt: "Due to packet trimming, it is very
rare for a packet to be actually lost... the sender can know very quickly if a
packet was actually lost. With eight packet switch queues... the worst-case
network RTT is approximately 400 microseconds... This allows a very short
retransmission timeout" (p.33), so RTO is a backstop "senders rarely need to
rely on" (p.35): roughly one extra RTT of latency, paid in header bandwidth,
never touching the timeout path.

**Does anyone contemplate not repairing a trim?** Searching all texts for
partial delivery, unreliable mode, or application-level loss tolerance: NDP has
none, every trimmed packet is retransmitted; its only tolerance concept is
reordering, not loss. EQDS comes closest: "EQDS provides a highly reliable
service, but it does not guarantee no packet loss whatsoever. A full
reliability guarantee would prevent EQDS managing its own state effectively,
risk resource starvation attacks, and would be pointless as full reliability
requires end-to-end acknowledgment whereas EQDS may be implemented in the NIC so
cannot protect data all the way to the receiving process" (extraction p.4). That
is a tunnel-layer admission bounded by implementation reality, not a design
choice letting an application forgive loss; EQDS still repairs what it can. UET
has UUD (Unreliable Unordered Delivery): "a basic datagram service... best-effort
delivery... There is no acknowledgement for the unreliable delivery mode" (UEC
v1.0.3 pp.233-235, per `uec-transport-brief.md`) - a real "accept what arrives"
primitive, but a blanket, connection-wide mode chosen at setup, not a receiver
decision to forgive specific trimmed ranges mid-flow; nothing ties UUD to
knowledge of which bytes were trimmed. MRC has no unreliable mode in either
paper: both describe only SACK/NACK reliable delivery plus reliability probes.
None of the four sources describes a receiver inspecting a trimmed range and
choosing, on its own criteria, never to pull or NACK it while advancing its
cumulative ACK past it.

**Is receiver-owned forgiveness a natural extension?** This is inference, not a
claim any source makes. NDP already gives the receiver authority over what to
pull and when - "the receiver is the only entity that can dynamically prioritize
its inbound traffic" (p.30) - and that authority already takes the shape a
bounded-loss transport needs: a per-connection queue of outstanding trimmed
ranges the receiver owns and paces. RCCC generalizes the same authority to
credit allocation across sources (UEC v1.0.3 pp.399-400), doubling the precedent that
the receiver decides who gets bandwidth. Choosing not to enqueue a PULL for a
given range, advancing the cumulative ACK past it instead, changes only the
receiver's local policy for what counts as wanted data; it needs no new wire
mechanism, since the receiver already knows which ranges were trimmed and
controls whether to request them. What is genuinely new: a NACK or SACK code
meaning "this range is permanently forgiven." None of NDP, EQDS, UET, or MRC
define one, so this piece needs new signaling, not just new receiver policy.

## Lineage table

| Feature | NDP (2017) | EQDS (2022) | UET (2025-2026) | MRC (2026) |
|---|---|---|---|---|
| Trimming | Strict priority queue, 10:1 WRR, forward to dest | NDP-derived loop where trimming available | Forward-to-dest only (bts out of scope); WDRR 25% share recommended | Forward to dest; NACK-triggering; also splits congestion vs. path-failure loss |
| Receiver pull/credit | Native: pull queue, per-sender pull counter | Direct: PULL packets carry credit, NDP-derived | RCCC, EQDS-derived, optional, incast-focused | Absent; NSCC (sender window) only |
| Default CC | None in Clos | Receiver credit | NSCC (sender, window, ECN+RTT); RCCC optional | NSCC only |
| Spraying | Sender-permuted path list | N/A (tunnel over existing transport) | Entropy pool, 64-256 values, adaptive | EV per packet; static SRv6, switch adaptive routing off |
| First-RTT full window | Yes, ~12-30 packets | Yes, NDP-derived burst before credit | Yes, "start at line rate" by design | Not stated (unverified) |
| RTO | Rare backstop | Not primary repair path | Backstop, MUST, exponential backoff | Backstop; linear-then-exponential (mandatory) |
| App loss tolerance | None | Layer-bounded reliability, not app-exposed | UUD: unreliable, connection-wide, no partial-range forgiveness | None in primary sources |

## References

- Handley et al., "Re-architecting datacenter networks and stacks for low
  latency and high performance," SIGCOMM '17, pp.29-42,
  https://s.joefang.org/ndp.pdf, accessed 2026-09-05.
- Olteanu et al., "An edge-queued datagram service for all datacenter traffic,"
  NSDI'22, https://www.usenix.org/system/files/nsdi22-paper-olteanu.pdf,
  accessed 2026-09-05.
- Bonato, Kabbani, De Sensi, Pan, Le, Raiciu, Handley, Hoefler et al.,
  "SMaRTT-REPS," arXiv:2404.01630v4, https://arxiv.org/pdf/2404.01630, accessed
  2026-09-05.
- Ultra Ethernet Consortium, *Ultra Ethernet Specification v1.0.3* (PDF, released
  2026-07-16, 574 pages), pp.233-235, 290-297, 356, 365-366, 384, 399-400, 456,
  459-464,
  https://ultraethernet.org/wp-content/uploads/sites/20/2026/08/UE-Specification-1.0.3.pdf,
  accessed 2026-09-05, cross-cited against
  `/config/repositories/astra-sim/docs/agents/uec-transport-brief.md`.
- Araujo, Handley et al., "Resilient AI Supercomputer Networking using MRC and
  SRv6,"
  https://cdn.openai.com/pdf/resilient-ai-supercomputer-networking-using-mrc-and-srv6.pdf,
  accessed 2026-09-05.
- Sohan, Spada, Davis, Handley et al., "The Multipath Reliable Connection (MRC)
  Transport," arXiv:2606.18170, https://arxiv.org/pdf/2606.18170, accessed
  2026-09-05.
- `/config/repositories/astra-sim/docs/agents/uec-transport-brief.md`, cited for
  UEC facts it already establishes (S1-S17 therein).

## Unverified list

- MRC's initial-window/first-RTT policy: neither primary MRC paper states
  whether a full window is sent unconstrained in the first RTT as NDP, EQDS,
  and UET's NSCC/RCCC do. Absence of text, not a contradiction.
- Any PCIe- or host-bus-specific reason for sender-based CC: searched
  SMaRTT-REPS and the UEC spec text on hand; the reasons found are fabric-wide
  congestion blindness of pure receiver control and NIC memory/state
  constraints, not PCIe. No PCIe-specific primary text was found.
- Whether any UEC or MRC text defines a NACK/SACK code meaning "this trimmed
  range is permanently forgiven": none found. The receiver-owned forgiveness
  argument in Part 3 is this author's inference from the pull/credit precedent,
  not a documented mechanism.
- UET design-principles paper (arXiv:2508.08906) was checked only in its first
  eight pages for receiver/sender-CC rationale; later pages not read.
- REPS and STrack (cited by the UEC spec and MRC papers for spraying) were not
  independently read here; already flagged unverified in
  `uec-transport-brief.md`.
