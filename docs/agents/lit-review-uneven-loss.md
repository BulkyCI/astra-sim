# Uneven per-worker gradient loss in an all-reduce: what the literature settles

Scoping review searched 2026-09-16 over OpenAlex, arXiv and Crossref with the
lit-review tool; session `uneven-gradient-loss-all-reduce-lbc52mhfhe9uivj9phkk2atk0o`.
59 logged queries and 3 snowball rounds returned 703 records, 603 after
dedup; 571 were excluded at title and abstract with a recorded reason and 32
were included. Twenty included papers were read in full, nine at abstract
level, and three remain unread; nothing below rests on the unread three.

## 1. The question

FORGIVE pools a loss budget per receiving rank per training step, so the
fabric chooses which sender's bytes a rank loses: rank B may receive 80 % of
worker A's contribution and 40 % of worker C's, 60 % on average, rather than
60 % from each, and the receiver zero-fills what never arrives without
rescaling the sum. Three questions follow. Does SGD's tolerance to bounded
gradient loss depend only on the aggregate fraction a rank receives per step,
or on how that loss spreads across the contributing workers? Does the answer
differ between the reduce-scatter half, where a missing contribution tilts
the reduced value toward the senders whose bytes arrived and shrinks the
effective batch on those elements, and the all-gather half, where a missing
reduced value leaves one replica's parameters different from every other
replica's? And what do the nearest systems assume about the distribution of
loss across senders?

## 2. The retrieved works

| # | work | venue, year | loss or participation model | rescaled | phase treatment | depends on the per-worker distribution |
| --- | --- | --- | --- | --- | --- | --- |
| [4] | Beznosikov et al., biased compression | JMLR 24, 2023 | per-worker biased compressor, each contracting its own gradient | no | sender-side | yes: divergence and stalling counterexamples |
| [3] | Ajalloeian and Stich, biased gradients | arXiv, 2020 | one aggregate bias, `\|\|b\|\|^2 <= m\|\|grad f\|\|^2 + zeta^2` | n/a | single oracle | no worker index exists |
| [2] | Wang et al., FedNova | NeurIPS, 2020 | unequal local step counts, hence unequal effective weights | weights sum to 1 | none | yes: tight floor `2 chi^2(p\|\|w) kappa^2` |
| [7] | Rodio et al., CA-Fed | INFOCOM, 2023 | per-client Markov availability, correlated in time | server weights q_k | none | yes: bias `2 kappa^4 chi^2(alpha\|\|p) Gamma` |
| [5] | Cho et al., power-of-choice | arXiv, 2020 | biased client selection correlated with local loss | 1/m over m selected | none | yes: floor `(8 L Gamma / 3 mu)(rho~/rho - 1)` |
| [6] | Wang and Ji, arbitrary participation | arXiv, 2022 | arbitrary per-round per-client weight q_t^n | sum to 1 assumed | none | yes: `rho^2 = sum_n (q_t^n)^2`, `delta~^2(P)` |
| [29] | Li et al., FedAvg on non-IID data | ICLR, 2020 | two unbiased sampling schemes only | 1/K or N/K | none | yes, and it declines to analyse the unrescaled case |
| [27] | Stich et al., sparsified SGD with memory | NeurIPS, 2018 | k-contraction compressor, one worker | error memory | none | single worker |
| [28] | Karimireddy et al., error feedback | ICML, 2019 | delta-approximate compressor, one worker | error memory | none | single worker; counterexamples without memory |
| [25] | Weintraub et al., training under packet loss | arXiv, 2025 | i.i.d. Bernoulli(p) per (sender, receiver) shard | yes, realized count | both halves, differently | no: one gradient expectation assumed for all senders |
| [24] | Yu et al., learning over unreliable networks | arXiv, 2018 | i.i.d. Bernoulli(p), identical on every link | yes, realized count | both halves, differently | no: symmetry invoked in the proof |
| [MLT] | Wang et al., MLT | NSDI, 2024 | switch drops by layer and magnitude; profiling uses i.i.d. zeroing | no, zero-fill | push and pull differ | no: worker variation maxed into a worst case |
| [16] | Wang et al., DLCP | arXiv, 2020 | as MLT, priority dropping by magnitude class | analysis divides by surviving senders | pull gets a lower bound | no |
| [32] | Chen et al., LTP | IWQoS, 2023 | receiver-driven early close; per-packet injected loss | no, bubble-filling | tolerance in gathering only | named, then excluded by assumption |
| [22] | Chen et al., trimmable gradients | HotNets, 2024 | one pre-set global trim probability, emulated | per-sender scale factors | none; 2 nodes | not addressed; one sender per receiver |
| [20] | Warraich et al., OptiReduce | arXiv, 2023 | emergent timeout and congestion loss | no | halves named, never split | not addressed; every figure is an aggregate |
| [12] | Koloskova et al., unified decentralized SGD | ICML, 2020 | doubly stochastic mixing, spectral gap p | mass preserving | all-gather analogue | no: consensus distance is an unweighted average |
| [19] | Kong et al., consensus control | ICML, 2021 | doubly stochastic mixing, controlled gossip | mass preserving | all-gather analogue | no, and the threshold is topology-free |
| [1] | ThrowRightAway | arXiv, 2021 | per-parameter Bernoulli(r) on the low-bandwidth group | yes, by 1/(1-r) | parameter server | no bound of any kind |
| [17] | CSA-UD | arXiv, 2026 | every lost packet is recovered | exact by construction | none | inapplicable; no loss is tolerated |
| [18] | Ma et al., DBLP | arXiv, 2026 | bursty loss at 60 to 90 % on a centralized reduce plus broadcast | no, zero-fill | none | not addressed; 3 workers |

## 3. What the theory says

No retrieved result covers a biased aggregate left unrescaled. Beznosikov et
al. build counterexamples in which every worker delivers an equal, bounded
fraction of its own gradient, Top-1 of a 3-vector, and the unrescaled average
diverges as `(1 + 11 eta / 6)^k` for every step size; a further construction
freezes the iterate at a non-optimal point, and their only positive
distributed theorem needs error-feedback memory at every worker [4].
Ajalloeian and Stich show that a perturbation staying a contraction of the
aggregate costs only a 1/(1-m) slowdown, while an additive component leaves
the floor `zeta^2/(1-m)` that no step size removes [3]. Karimireddy et al.
give the matching negative result for zero-fill without memory, since a
biased compressor can raise the objective in expectation at every step [28],
and Stich et al. take the same position and price the unbiased alternative at
a factor d/k [27].

Three independent groups put the damage in the same place. FedNova proves
that unequal unrescaled weights move the fixed point to the surrogate
`F~ = sum_i w_i F_i` and floor the true gradient norm at
`2 chi^2(p||w) kappa^2`, with a two-client lower bound showing the floor is
real [2]; Rodio et al. reach `2 kappa^4 chi^2(alpha||p) Gamma` from per-client
availability [7] and Cho et al. reach `(8 L Gamma / 3 mu)(rho~/rho - 1)` from
biased selection [5]. Each floor multiplies a per-worker mismatch by a
cross-worker heterogeneity term, and all three papers state that the floor
vanishes when the local objectives are identical [2][7][5]. Wang and Ji add
the part that survives homogeneity, since `rho^2 = sum_n (q_t^n)^2` is
minimized by equal weights at a fixed number of contributors [6].

The effective-batch reading of reduce-scatter loss is what the packet-loss
papers implement, and they rescale: Weintraub et al. divide by the realized
number of delivered contributions and prove the reduced shard stays unbiased
[25], Yu et al. divide by the realized received count and push the cost into
second moments of a random mixing matrix, giving `alpha_2 = O(p(1-p)/n)`
multiplying `(sigma^2 + 3 zeta^2)` [24], and TRA uses a per-group 1/(1-r)
[1]. MLT and DLCP are inconsistent here, implementing zero-fill in the data
path while their shared appendix averages over the surviving senders [MLT][16].
For the all-gather half, Koloskova et al. carry the consensus distance
`Xi_t^2` as an additive `+ gamma B Xi_t^2` term in the descent recursion [12],
and Kong et al. prove a strictly positive critical consensus distance
`Gamma_t^2 = gamma sigma^2 / (L n) + ||grad f||^2 / (8 L^2)` below which
decentralized SGD recovers the centralized rate, then price it by phase: on
ResNet-20 over 64 ranks the uncontrolled distance in the first phase costs
2.40 points of top-1 accuracy, the same distance in the middle phase gains
0.43 points, and in the last phase it costs 0.25 points [19]. Both assume a
doubly stochastic mixing matrix, so undelivered bytes fall outside their model
as written [12][19].

## 4. Verdict

Question 1, aggregate or distribution. Proven that the aggregate is not
sufficient once the sum is unrescaled: Beznosikov's counterexamples hold the
per-worker delivered fraction equal and bounded and still diverge [4], and
FedNova, Rodio and Cho each prove a non-vanishing floor set by a per-worker
mismatch multiplied by cross-worker heterogeneity [2][7][5]. Proven in the
other direction: when the sum is rescaled by the realized delivered count and
every worker's gradient shares one expectation, the aggregate suffices, which
is exactly what Weintraub et al. and Yu et al. assume and use [25][24].
Empirical: Weintraub et al. measure 10 % loss at 1.17 % worse validation
perplexity and 40 % at 6.65 % on LLaMA-2 7B over 64 GPUs [25], MLT profiles
0.7 to 3.3 % of gradient bytes at equal rounds and runs its evaluation at a
10 % bound [MLT], DLCP profiles 0.6 to 3.5 % [16], and TRA keeps accuracy at
10 % and breaks at 50 % with its correction in place [1]. Unmeasured: no
retrieved paper compares uneven with even loss at equal aggregate inside an
all-reduce. The one matched-aggregate comparison in the corpus is Wang and
Ji's client-selection ablation, where even and uneven selection of 10 of 250
clients give similar performance with a marginal edge to the even arm,
reported without numbers [6].

Question 2, whether the halves differ. Proven for the halves as modelled, and
the systems literature agrees with the theory. Weintraub et al. treat the two
halves with different mechanisms, count-rescaled averaging in the
reduce-scatter and stale-value retention in the all-gather, and bound the
steady-state replica gap at `lim E[D_t^2] = 2p/(1+p) sigma^2`, independent of
t and of the worker count [25]. Yu et al. rescale in the first half, fall back
to the receiver's own block in the second, and record that the resulting
mixing matrix is not doubly stochastic [24]. Three transports set a different
bound for the second half on purpose: DLCP enforces a lower bound on the pull
stage "because each gradient in the pull stage is in nature aggregated from
many workers, thus more important" [16], LTP allows loss only in the gathering
stage and none in broadcasting so that replicas stay consistent [32], and MLT
zero-fills lost gradients but substitutes the previous iteration's value for
lost parameters, then marks all parameter packets important under FSDP where
that fallback is unavailable [MLT]. Kong et al. supply the tolerance statement
for the second half, a strictly positive and topology-free critical consensus
distance, together with the phase asymmetry [19]. Unmeasured: none of these
papers quantifies a separate tolerated fraction for the second half, neither
packet-loss paper separates the drop rates of the two halves since a single p
governs both [25][24], and no retrieved paper measures replica divergence
under zero-fill rather than stale retention.

Question 3, what the nearest works assume. Uniform and i.i.d. is the norm.
Weintraub et al. draw an independent Bernoulli(p) per (sender, receiver) shard
and name bursty and correlated loss as open [25]; Yu et al. assume one
probability on every link and invoke symmetry explicitly in the proof [24];
MLT and DLCP both let the switch drop by layer and magnitude, then collapse
worker-to-worker variation into a worst-case constant in the proof [MLT][16];
the HotNets trimming paper uses one global probability on a two-node testbed,
where a receiver has one sender and cross-sender unevenness cannot arise [22];
OptiReduce reports only aggregate byte fractions and concedes its drops
include what a slow worker could not send before its timeout, which by
construction repeats on the same worker, without measuring it [20]; DBLP
injects bursty loss at one receiver across 3 workers [18]. Two works name the
problem. LTP states that "different worker nodes may have different gradient
arrival rates, which leads to bias in the contributions from different worker
nodes", then assumes homogeneous networks so the arrival rates stay even and
leaves the fix as ongoing work [32]. MLT's gray-failure experiment injects
0.01, 0.1 and 1 % loss on one worker's link, which is uneven loss by
construction, and reports only aggregate training speed [MLT]. Unmeasured, on
the evidence of null probes s47, s51 and s52: no retrieved paper measures
uneven per-worker loss inside an all-reduce.

What this implies for the ledger. Rodio's result says an uneven per-worker
participation moves the fixed point with a bias proportional to the
cross-worker heterogeneity Gamma, and the bias is zero when the local
objectives are identical [7]; FedNova and Cho reach the same conditional
[2][5]. Our setting is single-dataset data-parallel training with shuffled
shards, where every rank's gradient estimates the same expectation and Gamma
is near zero, so a pooled per-receiver budget with no rescaling does not move
the optimum by the mechanism those three papers prove. What survives
homogeneity is the shrinkage and the concentration cost: an unrescaled sum is
a shrunken gradient, equivalent to a per-step learning-rate cut equal to the
delivered fraction under Wang and Ji's normalization [6], and `rho^2` rises as
the delivered mass falls on fewer senders [6]. TRA's 1/(1-r) removes the
shrinkage at group granularity [1]; the per-sender analogues are FedNova's
normalization by each worker's realized progress [2] and Weintraub's division
by the realized delivered count [25]. A per-sender budget instead equalizes
every sender's delivered fraction by construction, which zeroes the
chi-square mismatch and minimizes `rho^2` without the receiver knowing any
sender's delivered fraction, at the cost of the pooling gain. The pooled
budget with a per-sender rescale at the receiver is the third option, and no
retrieved paper evaluates it.

## 5. The experiment that would settle it

Run it on the GPT-2-S rig the May work used, 125M parameters on the same
data-parallel setup, with the collective changed to reduce-scatter plus
all-gather rather than the centralized reduce plus broadcast DBLP ran [18],
and at 8 ranks or more so that per-sender skew exists. Take the pattern from
our own bundles: for each (sender, receiver, step) compute the delivered
fraction from `seed_<seed>/<arm>/telemetry/flow_events.csv` joined to
`collective_events.csv`, which gives an empirical matrix at the budget under
test. Run five arms at equal total bytes lost per receiving rank per step.
Arm 1 replays the measured matrix. Arm 2 spreads the same per-receiver total
evenly across senders. Arm 3 applies the measured matrix to the
reduce-scatter half only. Arm 4 applies it to the all-gather half only. Arm 5
replays the measured matrix and rescales each sender's contribution by its own
delivered fraction. Report validation perplexity, the per-rank mismatch
`sum_i (1/G - w_i)^2 / w_i` and `rho^2` per step, and for arms 3 and 4 the
consensus distance `Xi_t^2 = (1/G) sum_i ||x_bar - x_i||^2` against Kong's
critical value [19]. Arm 1 against arm 2 answers question 1 at equal
aggregate, arm 3 against arm 4 answers question 2, arm 5 prices the
correction, and the mismatch and `Xi_t^2` traces say which theory, the biased
fixed point or the consensus distance, explains the effect.

## 6. References

Read in full this session from the PDF named, with the retrieval source in
brackets.

| # | work | identifier | source |
| --- | --- | --- | --- |
| [1] | Loss Tolerant Federated Learning (ThrowRightAway), 2021 | arXiv:2105.03591 | OpenAlex |
| [2] | Wang, Liu, Liang, Joshi, Poor, Tackling the Objective Inconsistency Problem (FedNova), NeurIPS 2020 | arXiv:2007.07481 | OpenAlex |
| [3] | Ajalloeian, Stich, On the Convergence of SGD with Biased Gradients, 2020 | arXiv:2008.00051 | OpenAlex |
| [4] | Beznosikov, Horvath, Richtarik, Safaryan, On Biased Compression for Distributed Learning, JMLR 24, 2023 | arXiv:2002.12410 | OpenAlex |
| [5] | Cho, Wang, Joshi, Client Selection in Federated Learning, 2020 | arXiv:2010.01243 | Crossref |
| [6] | Wang, Ji, A Unified Analysis of FL with Arbitrary Client Participation, 2022 | arXiv:2205.13648 | OpenAlex |
| [7] | Rodio, Faticanti, Marfoq, Neglia, Leonardi, FL under Heterogeneous and Correlated Client Availability, INFOCOM 2023 | doi:10.1109/INFOCOM53939.2023.10228876 | OpenAlex |
| [12] | Koloskova, Loizou, Boreiri, Jaggi, Stich, A Unified Theory of Decentralized SGD, ICML 2020 | PMLR 119, appendices arXiv:2003.10422 | Crossref |
| [16] | Wang et al., DLCP, Domain-specific Communication Optimization for Distributed DNN Training, 2020 | arXiv:2008.08445 | arXiv |
| [17] | Communication-Semantic-Aware RDMA Loss Recovery (CSA-UD), 2026 | arXiv:2606.20582 | arXiv |
| [18] | Ma, Qu, Yi, Lin, Ganjali, DBLP: Phase-Aware Bounded-Loss Transport, 2026 | arXiv:2605.01989 | arXiv |
| [19] | Kong, Lin, Koloskova, Jaggi, Stich, Consensus Control for Decentralized Deep Learning, ICML 2021 | arXiv:2102.04828 | arXiv |
| [20] | Warraich, Shabtai, Zhang, Kim, Canini, OptiReduce, 2023 | arXiv:2310.06993 | OpenAlex |
| [22] | Chen, Vargaftik, Ben Basat, When ML Training Cuts Through Congestion, HotNets 2024 | doi:10.1145/3696348.3696880 | OpenAlex |
| [24] | Yu et al., Distributed Learning over Unreliable Networks, 2018 | arXiv:1810.07766 | arXiv |
| [25] | Weintraub, Banner, Orda, Distributed Training under Packet Loss, 2025 | arXiv:2507.07114 | arXiv |
| [27] | Stich, Cordonnier, Jaggi, Sparsified SGD with Memory, NeurIPS 2018 | arXiv:1809.07599 | arXiv |
| [28] | Karimireddy, Rebjock, Stich, Jaggi, Error Feedback Fixes SignSGD, ICML 2019 | arXiv:1901.09847 | arXiv |
| [29] | Li, Huang, Yang, Wang, Zhang, On the Convergence of FedAvg on Non-IID Data, ICLR 2020 | arXiv:1907.02189 | arXiv |
| [32] | Chen, Shi, Liu, Ai, Liu, Xu, LTP, IWQoS 2023 | doi:10.1109/IWQoS57198.2023.10188699, read from arXiv:2305.04279v1 | OpenAlex |
| [MLT] | Wang, Tian, Wan, Xia, Zeng, Wang, Chen, Chen, Bai, Jiang, Towards Domain-Specific Network Transport for Distributed DNN Training, NSDI 2024 | usenix.org/system/files/nsdi24-wang-hao.pdf | fetched page |

Marker numbers come from the session's append-only citation table, so the
gaps belong to corpus records this note does not cite.

MLT has no OpenAlex, Crossref or arXiv record (probes s48, s57, s58,
s59), so it is a fetched-page citation rather than a corpus record. DBLP [18]
was read in full on 2026-09-05, with page citations in
`dblp-paper-detailed-read.md`. Read at abstract level and uncited above:
Warraich's bounded-loss dissertation doi:10.25394/pgs.30885710.v1, McMahan et
al. arXiv:1602.05629, Lin et al. arXiv:1712.01887, Aji and Heafield
doi:10.18653/v1/D17-1045, Strom doi:10.21437/Interspeech.2015-354 with its
abstract fetched from the ISCA archive, Lian et al. arXiv:1705.09056, Stich
arXiv:1805.09767, Moshpit SGD arXiv:2103.03239, NetApprox arXiv:1901.01632.
Included but unread this session, so nothing above rests on them: Dutta et al.
arXiv:1803.01113, Recht et al. arXiv:1106.5730, Karimireddy et al.
arXiv:2006.09365.

## Limits of this review

The included set is 32 papers against the guide's band of 10 to 25, three of
them unread, and the level was amended from full to lite scoping mid-session
when the budget was cut. Every OpenAlex query that returned more than its
limit is a ranked sample, with upstream totals in the search log. Crossref
relevance search proved noisy for title lookups, so several named seeds
entered through arXiv instead. The gap claim in question 3 rests on three
zero-result arXiv probes, s47 (`loss tolerance` and `LLM` and `training`), s51
(`reduce-scatter` and `packet loss`) and s52 (`all-gather` and `loss` and
`transport`).
