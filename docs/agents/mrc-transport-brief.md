<!-- Source: Araujo et al. arXiv:2605.04333 and Sohan et al. arXiv:2606.18170, both read in full; secondary vendor blogs as noted inline. Read 2026-09-05. -->

# MRC (Multipath Reliable Connection): Sourced Brief

For a research programme simulating bounded-loss gradient transport on a UEC-style trimming fabric in ASTRA-sim plus ns-3. Every claim is cited. Access date for web sources: 2026-09-05. UET facts referenced below (NSCC, RCCC, trimming, PDC) are covered in full in [uec-transport-brief.md](uec-transport-brief.md).

Primary sources, read in full:
- [P1] Araujo, Chow, Handley et al., "Resilient AI Supercomputer Networking using MRC and SRv6," arXiv:2605.04333, PDF at cdn.openai.com (18 pages).
- [P2] Sohan, Spada, Davis et al., "The Multipath Reliable Connection (MRC) Transport," arXiv:2606.18170 (5 pages).

## A. Loss recovery

**SACK/NACK.** "Each SACK carries a cumulative acknowledgment, a bitmap offset, and a bitmask of out-of-order arrivals relative to that offset. This mechanism enables the requestor to explicitly distinguish packet loss from transient reordering" [P2, Sec. II-C]. NACKs are separate and proactive: "negative acknowledgments (NACKs) provide proactive non-delivery signaling to trigger immediate retransmissions... driven by deterministic events such as trimmed packet arrival or local resource exhaustion" [P2, Sec. II-C]. Retransmission targets the oldest gap first, using "a differentiated, higher-priority traffic class" [P2, Sec. II-C]. On the wire these use new headers (SETH, NETH, PETH) appended to a modified BTH [P2, Table II].

**Go-back-N does not survive.** "RC is single-path with go-back-N retransmission" [P2, Sec. I] describes what MRC replaces; MRC's trim-plus-NACK path exists "to trigger precise retransmission, avoiding Go-Back-N" [Keysight blog, 2026-06-04]. RC and MRC are "non-interoperable" [P2, Sec. III], so go-back-N is not a fallback within MRC.

**RTO.** Mandatory: "Linear + Exponential ACK timeout: Retransmit timer scales linearly before transitioning to exponential backoff" [P2, Table I], plus an optional per-packet timer. Requesters can also proactively query state via reliability probes instead of waiting on a timer [P2, Sec. II-C].

**Trimming.** "MRC supports packet trimming where switches truncate logically dropped packets, forwarding only their headers via a high-priority traffic class. Responders process these headers to generate a NACK... This explicit, low-latency loss signal enables fast retransmissions that bypass retransmit-timeout timers" [P2, Sec. II-C]. Operationally: "a packet that would have been dropped due to congestion has its payload trimmed off and is priority-forwarded to the destination. The receiving NIC then generates a NACK to trigger fast retransmission" [P1, Sec. 2.1].

**Trim = congestion signal; real loss = path-failure signal.** This distinction is explicit and central: trimming "lets MRC distinguish congestion loss from other packet loss, which in AI clusters is mostly due to link flaps and failures" [P1, Sec. 2.1]. "When a packet is not trimmed but actually lost, MRC assumes the path has failed and immediately stops using the corresponding EV" [P1, Sec. 2.1]. Because not all untrimmed loss is a true failure, "MRC sends background path probes to determine whether paths it assumed were bad are actually bad... If enough probes succeed, the EV is resurrected" [P1, Sec. 2.1]. Overall: "a transport protocol that can detect path failures and bypass them in a few tens of microseconds" [P1, Sec. 2.1].

**RoCE vs MRC under induced loss, by message size.** Testbed: 64 GPUs, AMD Pollara/Broadcom TH5, loss injected via inline P4 at 0.1% and 1% on all planes, 64-way ring all-reduce (Fig. 16) and all-to-all (Fig. 17), message sizes 4MB-16GB [P1, Sec. 5.2.7]. Values are graphical, not tabulated. At 0.1% loss: "MRC is more resilient - with large message sizes it can retransmit fast enough that 0.1% loss has little impact. At smaller message sizes... recovering packet losses has more impact" [P1, Sec. 5.2.7]. At 1% loss: "RoCE is pretty much unusable and even MRC only gets around a third of the intended throughput" [P1, Sec. 5.2.7]. For all-to-all: "At large message sizes and 0.1% loss, RoCE barely sees any degradation... At small message sizes... RoCE does very poorly. MRC's SACK-based retransmission helps greatly here" [P1, Sec. 5.2.7]. Baseline, no loss: "RoCE with one QP... generally achieves only half the possible throughput... very little gain beyond 8 QPs," vs. "one MRC QP spraying across 256 paths achieves better performance than 16 QPs" [P1, Sec. 5.2.7]. This loss test hits all eight planes at once, worse than production where a bad plane is simply denylisted [P1, Sec. 5.2.7].

## B. Congestion control

**NSCC.** "A sender-based window-driven algorithm that utilizes ECN and RTT-derived queueing delay to regulate a byte-fidelity congestion window" [P2, Sec. II-D]; listed as "Window-based, SACK-clocked ECN+RTT algorithm over best-effort Ethernet" [P2, Table I]. Every SACK carries CC telemetry: "forward-path ECN markings, responder accounting metrics..., and responder-side congestion window penalties" [P2, Sec. II-D]. AMD states NSCC's UEC lineage: "AMD contributed the NSCC congestion control algorithm, now part of the UEC Congestion Control specification" [AMD blog, via search synthesis; direct fetch timed out, see Unverified].

**Tiered "EV switch" response.** Not phrased this way in P1/P2, but stated directly by Keysight: "Mild congestion... triggers an immediate EV switch, steering the packet to a different path. Severe or widespread congestion triggers rate reduction, now controlled by a send window driven by combined ECN and RTT signals (NSCC), not by PFC pause frames" [Keysight blog]. P1 corroborates the path-first mechanism: ECN is enabled on all but the last hop and "the receiver echoes the ECN signal back to the sender, indicating that this specific path is more congested than others, and the sender temporarily avoids it" [P1, Sec. 2.1]. Demonstrated live: on ECN-detected congestion between two flows sharing an EV, "MRC triggers traffic redistribution to rebalance load across the available EVs... without observable performance degradation" [P1, Sec. 5.2.5].

**Receiver credit / bounded in-flight.** Maximum PSN Range (MPR): "a sliding receive window that strictly bounds in-flight request packets: a requestor cannot send a packet with a sequence number beyond the upper edge of the responder's advertised packet tracker bitmap" [P2, Sec. II-B], optionally dynamic via SACKs. A separate bound limits "the number of concurrent outstanding WriteIMM operations" [P2, Sec. II-B]. Generic "responder host backpressure" lets NSCC "modulate the requester's congestion window, preventing responder-side memory contention from degrading end-to-end performance" [P2, Sec. II-D].

**Incast specifically.** Strong empirical results but a guarded analytic caveat. In a 7-to-1 incast with a victim flow, "MRC almost perfectly shares the bottleneck link among the incast flows and has no impact on the victim flow" [P1, Sec. 5.2.8], versus RoCEv2+DCQCN where victim-flow throughput "degrades by about 25%" (1 QP) or drops "75%... from optimal" in one-second intervals (8 QPs) [P1, Sec. 5.2.8]. With PFC alone, "the victim flow only achiev[ed] 30 to 100Gbps depending on ECMP path choice and fairness" [P1, Appendix]. Against this, Keysight states: "for incast scenarios, MRC has no definitive answer, and given the inherent latency of ECN and RTT feedback, some retransmissions are likely unavoidable" [Keysight blog]. This gap matters for Section F.

**PFC disabled, quoted reasoning.** "Spraying is hard to combine with the priority flow control (PFC) mechanism used in lossless Ethernet because a single flow reaches the last-hop switch over hundreds of paths. Further, PFC tends to create head-of-line blocking between different collectives, hurting tail latency. Thus MRC disables PFC and uses Ethernet in best-effort (lossy) mode" [P1, Sec. 2.1]. Field practice concurs: "configuring DCQCN properly is very hard... some hyperscalers have disabled it in production" [P1, Sec. 5.2.8].

## C. Multipath

**SRv6, static paths.** "We use the micro-segment ID (uSID) format, where the destination IPv6 address consists of a 32-bit locator prefix followed by a sequence of 16-bit uSIDs each corresponding to a specific switch along the path" [P1, Sec. 2.2]. "This forwarding table was configured when the switch was installed, and is generally never changed" [P1, Sec. 2.2]. Packets are "IPv6 in IPv6 encapsulated, with the outer destination address being the SRv6 path and the inner destination address containing the destination NIC's own address" [P1, Sec. 2.2].

**Adaptive spraying at the NIC; switch adaptive routing disabled.** "We took the unusual position of disabling dynamic routing in the switches because we didn't want two adaptive routing mechanisms interacting with each other" [P1, Introduction]. "MRC reacts to a failure first, avoiding the broken path; then dynamic routing re-routes... when running MRC, dynamic routing caused more problems than it solved, so we simply disabled it" [P1, Sec. 2.2].

**Entropies per connection.** "At QP startup, the sender generates an EV set for that QP—typically 128 to 256 entries" [P1, Sec. 2.1], "plus a backup EV set for failures" [P1, Sec. 2.4]. Each EV state: "GOOD, SKIP, DENIED, or ASSUMED_BAD. Only EVs in the GOOD state are used for transmission" [P2, Sec. II-A].

**Reordering / direct data placement.** "Every data packet contains the RDMA virtual address and remote key so the receiving NIC can write each arriving packet to memory immediately, no matter the arrival order" [P1, Sec. 2.1]; P2 frames this generally as permitting "out-of-order data placement at the responder... to tolerate packet spraying and decouples packet delivery from semantic processing" [P2, Sec. II].

**Effect on core congestion / variance.** One MRC QP over 256 paths beats 16 RoCE QPs [P1, Sec. 5.2.7]; near-perfect incast fairness [P1, Sec. 5.2.8]. The goal is framed as tail, not mean: "synchronous pretraining does not care about mean performance—only the tail matters" [P1, Sec. 5.2.7]. Field example: a transceiver glitch flapping four links caused "throughput [to suffer] approximately a 25% reduction over the minute of flaps, then recovered to full speed immediately afterwards. The job did not crash" [P1, Sec. 5.1].

## D. Numbers

**Scale/topology.** Deployed "2-Tier 8x100 Gb/s multi-plane topology" reaching "131,072 NICs (8 planes)" [P1, Fig. 1]. Four experimental clusters [P1, Table 1]: A (GB200+ConnectX-8 800Gbps, Spectrum-4/Broadcom TH5, 4x200Gbps multi-plane); B (GB200+ConnectX-8 800Gbps, Spectrum-5, 8x100Gbps); C (AMD MI355+Pollara 400Gbps, TH5, 4x100Gbps); D (RTX 6000+Thor Ultra, TH5, 400Gbps single-plane). Per secondary source, MRC is "already deployed across all of OpenAI's largest NVIDIA GB200 supercomputers... including... Oracle Cloud Infrastructure (OCI) in Abilene, Texas, and in Microsoft's Fairwater supercomputers" [Keysight blog].

**Point-to-point (Cluster B, CX-8):** T0-Local 2B latency 5.09us, 32KB bandwidth ~770 Gb/s (96% of peak); Cross-T1 2B latency 6.54us, 32KB ~770 Gb/s [P1, Sec. 5.2.1].

**NCCL at scale.** "NCCL over MRC achieves up to 92 GBytes/s for large message sizes at 42K GPUs" [P1, Sec. 5.2.6].

**Failure recovery timing.** Path bypass "in a few tens of microseconds" [P1, Sec. 2.1]. NIC port failure remap "typically takes a few seconds" [P1, Sec. 3]. A T1 switch reboot: down at t=0, "fully resumed forwarding by t=2 mins," "around 580K packets were dropped," throughput "largely unaffected afterwards" [P1, Sec. 5.1].

**Loss-rate/startup.** During a 75K-GPU job startup, "the loss rate across the whole job falls well below [1 loss/sec/NIC, i.e. 1 in 25 million at 800Gb/s] within a couple of minutes... even in the first minute less than 5 packets per QP are lost" [P1, Sec. 2.4].

**Topology failure-impact.** "Losing a T0-T1 link reduces capacity from a node by 3% in an 800Gb/s plane, vs 0.4% in a 100Gb/s plane"; losing a NIC-T0 link loses "12% of the NIC bandwidth" [P1, Sec. 2].

**NICs/switches.** "NVIDIA ConnectX-8, AMD Pollara and Vulcano, and Broadcom Thor Ultra" NICs; "NVIDIA Spectrum-4 and 5 switches running both Cumulus and SONiC," and "Arista... EOS on Broadcom Tomahawk 5 switches" [P1, Introduction].

## E. Relation to UEC/UET

**What MRC takes.** "Draws upon lessons from Ultra Ethernet Transport (UET)... Like UET, MRC employs packet spraying, adaptive load balancing based on ECN, out-of-order memory placement of received data, selective retransmission, and uses packet trimming to mitigate incast" [P1, Introduction]. NSCC itself is UEC-lineage, cited to the UEC v1.0.1 specification [P2, Sec. II-D, ref. 6].

**Where it differs.** "Unlike UET, MRC is a minimal extension to RoCE; MRC leverages and extends the existing Verbs API" [P1, Introduction]; it "extends RC directly" rather than following a clean-slate design [P2, Sec. I]. Routing: "In contrast to most existing works which use host-driven ECMP routing or switch spraying, MRC uses source routing with SRv6" [P1, Related Work]. Scope: "MRC narrows data-plane operations to Write and Write-with-Immediate... and removes RC end-to-end flow control in favor of explicit bounded-flight mechanisms" [P2, Sec. II].

On "no PDC": neither paper uses the term "Packet Delivery Context." Not addressed by any source read; see Unverified.

**Unreliable/partial-delivery mode.** None found. "At the transport level, only the RDMA write and write-with-immediate operations are supported" [P1, Introduction]; the OCP repo confirms "READ, SEND, or ATOMIC operations are not permitted" [OCP GitHub README]. Every data path is SACK/NACK-reliable (Sections A-B), reading as "every connection fully reliable," but the formal OCP spec PDF was inaccessible (HTTP 403), so a wire-level delivery-class definition could not be checked directly.

## F. For the bounded-loss simulation programme

The documented "cost of a lost packet" is consistently small and localized:

- **Trimmed (congestion) loss**: one repair RTT via immediate NACK, "bypass[ing] retransmit-timeout timers" [P2, Sec. II-C]. No per-trim window cut is stated in either paper; NSCC's rate response is gated on aggregate ECN/RTT/backpressure, not a single trim event (not established either way by the sources; see Unverified).
- **Genuine path-failure loss**: a path switch, not a payload cut. "Immediately stops using the corresponding EV" and reroutes within "a few tens of microseconds" [P1, Sec. 2.1]; "the missing packet is selectively retransmitted on a different path, and the impact on the job is negligible" [P1, Sec. 3].
- **Bytes re-carried**: limited to the specific missing PSNs identified by the SACK bitmap, not a go-back-N burst [P2, Sec. II-C].
- At sustained pathological loss (0.1-1% on all planes at once) the cost becomes throughput-proportional: "at 1% loss... even MRC only gets around a third of the intended throughput" [P1, Sec. 5.2.7], though the paper calls this a worst case unrepresentative of production per-plane operation.

**Incast evidence a bounded-loss policy could exploit.** The 7-to-1 incast experiment [P1, Sec. 5.2.8, Figs. 18/21/22] is the clearest candidate: RoCEv2+PFC/DCQCN measurably harms an unrelated victim flow (25-75% degradation, or a 30-100 Gbps floor) for the incast's duration, while MRC reportedly shares the bottleneck cleanly with no victim impact. This is a small 16-server synthetic testbed (Cluster D), not production-scale, and Keysight's caveat that MRC "has no definitive answer" for incast is not corroborated with data of its own.

**What the sources explicitly do not say.** No production-scale distribution of "cost of a lost packet" in bytes, microseconds, or completion-time percentiles exists; the RoCE/MRC comparison is a 64-GPU testbed with synthetic uniform loss, not a production trace. Whether NSCC's window is ever cut by a single trimmed/NACKed packet versus only by aggregate signals is not settled. No numeric incast frequency/duration distribution from live training traffic appears anywhere; Figs. 6-8 in P1 are single illustrative incidents, not a statistical sample. The OCP MRC 1.0 spec (exact RTO constants, SACK bitmap width, formal delivery-class definitions) was inaccessible (HTTP 403); anything above attributed to "the specification" is via P1/P2's description of it. Figures 16 and 17 are graphical only; no tabulated throughput numbers could be extracted beyond the qualitative text quoted in Section A.

## Comparison Table: UET vs MRC vs Classic RoCEv2

| Dimension | UET | MRC | Classic RoCEv2 (RC) |
|---|---|---|---|
| Loss recovery | Selective retransmission, packet trimming for incast [P1, Intro] | SACK (cumulative+bitmap) + proactive NACK on trim/resource exhaustion; linear-then-exponential RTO; optional per-packet timer [P2, Sec. II-C] | Go-back-N [P2, Sec. I] |
| Congestion control | Source of NSCC (UEC 1.0 CC spec) [P2, Sec. II-D] | NSCC: window-based, SACK-clocked, ECN+RTT [P2, Table I]; tiered EV-switch-then-rate-cut [Keysight] | PFC-based lossless, or DCQCN [P2, Sec. I] |
| Multipath | Packet spraying, adaptive LB, out-of-order placement [P1, Intro] | Per-packet EV spraying (100-256+ EVs/QP); SRv6 uSID static source routing; switch adaptive routing disabled [P1, Sec. 2.1-2.2] | Single path per QP, ECMP 5-tuple hash [P2, Sec. II-A] |
| Lossless fabric required | Targets best-effort [P1, Intro] | No; PFC disabled, "best-effort (lossy) mode" [P1, Sec. 2.1] | Typically yes (PFC), or DCQCN as lossy alternative [P1, Sec. 5.2.7] |
| Unreliable/partial-delivery mode | Not established by sources here | None found; Write/Write-Imm only, fully SACK-reliable [P1, Intro; OCP README] | N/A, RC fully reliable |
| Extends existing HW/API | Clean-slate stack [P1, Intro] | Minimal RoCE/Verbs extension, non-interoperable wire format [P1, Intro; P2, Sec. III] | Baseline IBTA/RoCEv2 |

## References

1. Araujo et al. "Resilient AI Supercomputer Networking using MRC and SRv6." arXiv:2605.04333, 2026. cdn.openai.com/pdf/resilient-ai-supercomputer-networking-using-mrc-and-srv6.pdf. Accessed 2026-09-05.
2. Sohan et al. "The Multipath Reliable Connection (MRC) Transport." arXiv:2606.18170, 2026. arxiv.org/abs/2606.18170. Accessed 2026-09-05.
3. NVIDIA. "Spectrum-X Ethernet and MRC." blogs.nvidia.com/blog/spectrum-x-ethernet-mrc/. Accessed 2026-09-05.
4. AMD. "Next Gen Networking Transport for Large Scale AI Training." amd.com/en/blogs/2026/next-gen-networking-transport-for-large-scale-ai-training.html. Accessed 2026-09-05; see Unverified, fetch timed out repeatedly.
5. Keysight. "MRC: A New Transport Protocol for AI Data Centers." keysight.com/blogs/en/tech/traf-gen/2026/06/04/mrc-a-new-transport-for-aidc. Accessed 2026-09-05, fetched directly, quotes verbatim-confirmed.
6. Open Compute Project. "OCP-Multipath-Reliable-Connection" repository. github.com/opencomputeproject/OCP-Multipath-Reliable-Connection. Accessed 2026-09-05.
7. Open Compute Project. "Multipath Reliable Connection (MRC) Specification v1.0," 2026. opencompute.org/documents/ocp-mrc-1-0-pdf. Attempted 2026-09-05, HTTP 403, not accessible.
8. Oracle Cloud Infrastructure blog. "First Principles: Unlocking Oracle Acceleron Multiplanar Fabric with MRC." blogs.oracle.com/cloud-infrastructure/first-principles-multipath-reliable-connection. Attempted 2026-09-05, HTTP 403; see Unverified.
9. Ultra Ethernet Consortium. "Ultra Ethernet Specification v1.0.1," 2025 (cited via P2, ref. 6; not independently fetched).
10. OpenAI. "Supercomputer networking to accelerate large scale AI training." openai.com/index/mrc-supercomputer-networking/. Not fetchable, HTTP 403; not used as a source.

## Unverified

- AMD blog (Ref. 4) and Oracle blog (Ref. 8): both blocked direct fetch (timeout, HTTP 403 respectively); attributed content (NSCC/UEC provenance, the Abilene/OCI Stargate deployment claim) is search-engine synthesis only, treat as paraphrase-level confidence.
- NVIDIA blog (Ref. 3): fetched directly, but NSCC, packet trimming, SACK/NACK internals, SRv6 mechanics, and numeric figures were absent from the page; only qualitative claims found there.
- OCP MRC 1.0 Specification (Ref. 7): inaccessible, HTTP 403. No wire-level detail (exact SACK bitmap width, RTO constants, EV field encoding beyond P1/P2, formal delivery-class definitions) has been checked against the primary spec text.
- UET "PDC" relationship (Sec. E): no source addresses this term; unresolved.
- Production incast statistics (Sec. F): no numeric frequency, duration, or tail-latency distribution from live training traffic in any source; P1's incast results are a small controlled testbed, not a production measurement.
- NSCC per-loss vs. aggregate-only window cut (Sec. F): not settled by any source read.
- Exact throughput values in Figs. 16-17 (RoCE vs MRC by loss rate/message size): graphical only in the source PDF, not tabulated in text.
