<!-- Produced 2026-09-05, reconciling docs/agents/uec-transport-brief.md (written from v1.0.2) against the newly confirmed UEC Specification v1.0.3. -->

# UEC v1.0.3 reconciliation note

## How this was read

The PDF was fetched with curl from
https://ultraethernet.org/wp-content/uploads/sites/20/2026/08/UE-Specification-1.0.3.pdf
(12.85 MB, HTTP 200). No local pdftotext/mutool/qpdf/pypdf was available, so
the file was extracted with the repo's `read-pdf` skill (a bundled Python
extractor), producing a plain-text layer tagged with `## PDF page N` markers
for all 574 pages. The title page confirms "Specification v1.0.3." Page
numbers below match the document's own printed page numbers. No image-only
or unreadable pages were found in the sections cited. A prior session's
cached v1.0.2 extraction in this scratchpad was used only to diff wording,
not trusted as a standalone source.

## What changed 1.0.2 to 1.0.3

The Release Notes (pp. 573-574) state that v1.0.3 was released 07/16/2026,
previous version 1.0.2 (01/21/2026), and that "this release includes a set
of editorial corrections and clarifications to improve the readability and
accuracy" of 1.0.2. The version-history line reads: "A number of editorial
clarifications, addition of 200 Gb/s per lane signaling, a new Negotiation
CP type, corrections to UE PHY CtlOS corruption protection, UE Transport
handling of retransmission when pds.flags.syn=1 on PDC close, specifying
MP_Range less than 128 and corrections to UE Link Layer to resolve CBFC/LLR
race conditions." The Impact Statement calls the clarifications
"non-substantive," but "Correction updates are required for conforming
implementations."

Three change-table entries touch the areas this brief cares about:

- Table 3-58, Table 3-61 (labeled "Clarification"): "Remove the
  UET_TRIMMED_ACK NACK code and clarify that trimmed ACKs do not generate a
  NACK." This is a real behavioral change to the NACK taxonomy, not merely
  editorial (see below).
- 3.5.5, 3.5.8, 3.5.16 (Correction): a new `Syn_Retx_Safety_Time` parameter
  fixes a PDC-establishment bug when a PDC is closed and reopened after a
  SYN-flagged packet is lost. Narrow edge case; does not touch the RTO
  backoff formula.
- 3.4.1.14, 3.4.5.3.2/.4.1, Table 3-17 (Clarification): UET_MSG_ERROR is
  confirmed not used with UUD PDCs, and UET_DATAGRAM_SEND's message ID must
  be 0. Narrows UUD's definition without changing its unreliable,
  uncontrolled-by-CC nature.

Nothing in the change list touches Section 4.1 trimming mechanics, NSCC,
RCCC, the SACK bitmap, or the RTO exponential-backoff formula; this was
confirmed independently by reading those sections directly, not just the
summary table.

## Corrections to the brief

Section 4.1 packet trimming (all verified, unchanged, pages moved by
roughly 8 due to document growth): MIN_TRIM_SIZE = 24 B for UET/UDP/IP
(Table 4-1) now p. 464 (was 456); "Fair-queueing allows trimmed packets to
consume no more than 50% of the bandwidth... WDRR with 25%... also a good
configuration option, at the expense of moderate trimmed packet loss in
large incasts" now p. 463 (was 455); back-to-sender out of scope ("This
specification focuses only on sending the trimmed packet to the
destination... is not part of this specification") now p. 459 (was 451);
DSCP_TRIMMABLE/DSCP_TRIMMED/DSCP_TRIMMED_LASTHOP configurable, Section 4.1,
pp. 460-464.

3.6.4.4 last-hop exclusion: verified verbatim, condition on RCCC still
present. "It is not used as a congestion signal to NSCC when RCCC is also
enabled, because RCCC can handle last-hop congestion by itself." Now p. 356
(was 349).

PDS modes RUD/ROD/RUDI/UUD: verified, substantively unchanged at pp.
233-235 (was 231-233). RUD uses selective retransmission; ROD's GoBackN
quote ("GoBackN drops all packets that arrive out of order, requiring the
source to retransmit all packets starting from the first missing PSN") is
identical; RUDI is at-least-once with no PDC/SES dedup state; UUD is
best-effort, not CC-controlled. One narrow addition: UET_DATAGRAM_SEND (the
UUD opcode) is now explicitly single-packet-message only with message ID
fixed at 0 (p. 157); this does not change the brief's UUD characterization.

SACK bitmap: verified, unchanged, p. 280 (Section 3.5.11.14). 64 bits; a
cleared bit means "no information about the PSN," not "not received."
Retransmission triggered by trimming, NACK, or RTO: verified, unchanged,
pp. 290-297. NACK codes UET_TRIMMED (0x01) and UET_TRIMMED_LASTHOP (0x02):
verified, unchanged, pp. 290-291.

**NACK code UET_TRIMMED_ACK (0x03): changed.** This is the one real content
break. In 1.0.3, code 0x03 in Table 3-58 is now "reserved," and Table 3-61
(p. 297) was rewritten: a trimmed RUD ACK or ROD ACK now reads "No,
retransmit the original RUD Request." No NACK is generated for a trimmed
ACK at all; the source instead relies on other loss detection (e.g. RTO) to
notice the missing ACK and retransmit the original request. This session's
cached v1.0.2 extraction showed RUD ACK/ROD ACK trimming generating
"UET_TRIMMED_ACK" at value 0x03, confirming the removal is a genuine
behavioral change, not just an editorial trim. Any codebase, including this
repo's, that special-cases a `UET_TRIMMED_ACK` NACK code should treat it as
removed: as of 1.0.3, a trimmed ACK does not generate a NACK.

RTO exponential backoff `RTO_TIMER = RTO_INIT_TIME * 2^retry_count`, range
0-8 s: verified verbatim, unchanged, p. 290 and p. 297.

NSCC window-based cwnd/inflight, ECN+delay dual signal, quick_adapt on
trims: verified, unchanged; Section 3.6.13 now begins p. 384 (was 377). The
quick_adapt pseudocode `if reason == UET_TRIMMED or (reason ==
UET_TRIMMED_LASTHOP and rccc == FALSE): adjust_cwnd = TRUE` is verified
verbatim in logic (minor line-wrap differences only), with the comment
"Only adjust the cwnd on a last hop trim if RCCC is not enabled" intact, now
p. 393 (was 385-386). The DCQCN rate-vs-window contrast sentence is
verified verbatim: "in a rate-based approach such as DCQCN, lack of
feedback is implied to be a sign of appropriate network operation, and the
rate is increased... in best-effort networks where packets may be silently
discarded due to congestion, increasing throughput in response to a lack of
congestion feedback results in poor performance." Now p. 365 (was 358).

RCCC receiver credit, EQDS-derived, incast handling, last-hop ECN disabled
when RCCC is on: verified, unchanged, pp. 399-400 (was 391-399; the range
shrank from tighter layout, not cut content). Incast quote intact: "To deal
with incast, RCCC leverages information available at the destination to
make optimal, instantaneous changes to the transmission rate of each of the
active sources."

SMaRTT-REPS and STrack citations: verified. NSCC's text reads "This section
specifies the NSCC algorithm, which is based on the SMaRTT [9] and Strack
[10] algorithms" (p. 384); the reference list (p. 456) gives full SMaRTT-REPS
and STrack arXiv citations. The brief's earlier page-68 citation does not
correspond to anything in 1.0.3; correct pages are 384 and 456.

Net verdict: every brief claim sourced from v1.0.2 is verified unchanged in
v1.0.3 except UET_TRIMMED_ACK, which is removed. All other differences are
page shifts from document growth, not content changes.

## New in 1.0.3 relevant to a bounded-loss gradient transport

Nothing adds a new "partial delivery" mode or an SES-layer reliability
choice beyond RUD/ROD/RUDI/UUD. UUD remains the only fire-and-forget,
not-CC-controlled primitive, and it gained clarifications that narrow
rather than expand it: UET_MSG_ERROR does not apply to UUD PDCs, and
UET_DATAGRAM_SEND is single-packet-message only with message ID fixed at 0
(p. 157). That makes UUD slightly more rigid as a building block for a
gradient-style transport, each send is one self-contained datagram with no
message-spanning semantics, worth noting for anyone composing a
bounded-loss transport on top of UUD rather than multi-packet messages.

On trimming under sustained incast, 1.0.3 carries forward 1.0.2's guidance
unchanged: WDRR at 25% "at the expense of moderate trimmed packet loss in
large incasts" (p. 463); RCCC (pp. 399-400), not trimming, remains the
spec's dedicated incast mechanism. No new statement addresses trimmed-packet
behavior specifically under sustained incast.

The UET_TRIMMED_ACK removal matters here too: a trimmed ACK no longer
produces a fast, explicit NACK signal and now falls back to RTO-based
detection or retransmission of the original request. For a design that
cares about the cost of losing acknowledgement packets specifically, this
is a real, if small, increase in expected recovery latency for that one
loss case relative to what v1.0.2 specified.

## Recommended parameter defaults for a simulator (NSCC/RCCC)

All from Section 3.6.13/3.6.17, pp. 390-419, unchanged from v1.0.2:
`config_base_rtt` is the round-trip time of the longest-path MTU-sized
packet with no other traffic, maintained to the nearest 128 ns (p. 390).
`BDP = min(sender.linkspeed, receiver.linkspeed) * config_base_rtt`
(p. 390). `target_qdelay` defaults to `0.75 * config_base_rtt` when trimming
is used, `1.0 * config_base_rtt` otherwise (p. 390).
`alpha = 4.0 * scaling_a * scaling_b * MTU / target_qdelay` (p. 390).
`max_wnd = 1.5 * sender.linkspeed * base_rtt` (p. 397) is the default
initial `ccc.cwnd` (Table 3-83, pp. 390-391). `qa_threshold`, the
quick_adapt delay trigger used only when trimming is disabled, is
`(drop_threshold / Plane_BDP - 1) * config_base_rtt`; with the recommended
tail-drop threshold of `5 * Plane_BDP` this equals `4 * target_qdelay`
(p. 390).

Switch-side recommended thresholds (pp. 418-419): probabilistic ECN marking
`queue_low.min_thresh = 0.2 * Plane_BDP`, `max_thresh = 0.8 * Plane_BDP`;
deterministic ECN threshold `0.5 * Plane_BDP` (probabilistic preferred);
trim threshold `Plane_BDP` for normal queues and `1.5 * Plane_BDP` for the
last-hop queue; drop thresholds `queue_med.drop_threshold =
queue_high.drop_threshold = Plane_BDP`, with a general tail-drop threshold
recommended between `2 * Plane_BDP` and `5 * Plane_BDP`. These let a
simulator size NSCC's window and switch queues for whatever link speed and
base RTT it simulates, rather than hand-picking fixed constants.

## References

Ultra Ethernet Consortium, *Ultra Ethernet Specification v1.0.3* (PDF,
released 07/16/2026), 574 pages,
https://ultraethernet.org/wp-content/uploads/sites/20/2026/08/UE-Specification-1.0.3.pdf,
accessed 2026-09-05.
