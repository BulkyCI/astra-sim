# Joe's writing invariants

Extracted from commit `93e1117`, where Joe rewrote 41 passages of
agent-drafted slide copy. Each invariant below is what changed, in his
direction, with his own before-and-after as the evidence. Ordered by how
many times the pattern fired.

Use this when drafting anything that goes out under his name.

## 1. Every clause gets an explicit subject. No verbless fragments.

Seven instances, the strongest signal in the sample. He also restores
dropped articles.

| drafted | his |
| --- | --- |
| "Now two measured axes." | "We measured two axes." |
| "184 commits, four cluster runs, about 180 simulated configurations at roughly five hours each." | "We made 184 commits and ran four cluster jobs across about 180 simulated configurations at roughly five hours each." |
| "Rule asked for a trim ratio of 0.5. Worst cell reached 0.24." | "The rule required a trim ratio of 0.5. The worst cell reached 0.24." |
| "64 ranks, selective repeat throughout, varying congestion control, fan-in and oversubscription" | "Across 64 ranks with selective repeat, we varied congestion control, fan-in and oversubscription" |
| "3.91 % of training time across sixteen seeds." | "Training time fell 3.91 % across sixteen seeds." |
| "recovered by letting the receiver forgive what the fabric trimmed" | "FORGIVE recovers this by letting the receiver forgive what the fabric trimmed" |

Telegraphic compression reads as a caption to him, not as writing. If a
line has no verb, it is not finished.

## 2. The actor goes in subject position, not the effect.

Six instances. He unwinds clefts, existentials and effect-first
constructions into agent, verb, object.

| drafted | his |
| --- | --- |
| "Six of the seven weeks went into the instrument" | "The instrument took six of the seven weeks" |
| "Hub-and-spoke pressure at one NIC is our fan-in 7 cell" | "Our fan-in 7 cell models hub-and-spoke pressure at one NIC" |
| "This is the confound that made us stop quoting the May headline." | "The overlap is the confound that prevents us from quoting the May headline." |
| "The three seeds that regress are the three where the policy added trims." | "The policy regresses on the three seeds where it adds trims." |
| "What we can now do is price it: the mask costs 3.2 points of time" | "The ledger prices the mask at 3.2 points of time" |
| "The policy flattens the worst seeds. On the four seeds whose worst all-reduce exceeds 1.3 s, that collective drops by 434 to 716 ms." | "On the four seeds whose worst all-reduce exceeds 1.3 s, the policy cuts that collective by 434 to 716 ms" |

## 3. Two short sentences become one subordinated clause.

Four instances. He does not write staccato pairs for emphasis; he joins
them with which, while, or a comma.

| drafted | his |
| --- | --- |
| "Every seed discards about the same two gigabytes. That number predicts nothing." | "Each seed discards about the same two gigabytes, which predicts nothing." |
| "Relief across our go-back-N arms runs 3.9 to 11.1 %. The selective-repeat arm buys 0.78 %." | "Relief across our go-back-N arms is 3.9 to 11.1 %, while the selective-repeat arm gains 0.78 %." |
| "The value comes from the recovery scheme. Change go-back-N to selective repeat and 3.9 to 11.1 % becomes 0.78 %." | "With selective repeat, relief drops from 3.9 to 11.1 % to 0.78 %." |

## 4. The condition or scope comes first.

Four instances. Where a claim holds is stated before the claim.

| drafted | his |
| --- | --- |
| "Discarding 1.98 GiB of gradient removed 156 GiB from the wire, because under go-back-N one trimmed packet rewinds a whole window." | "With go-back-N, discarding 1.98 GiB of gradient removed 156 GiB from the wire because one trimmed packet rewinds a whole window." |
| "Change go-back-N to selective repeat and 3.9 to 11.1 % becomes 0.78 %." | "With selective repeat, relief drops from 3.9 to 11.1 % to 0.78 %." |

## 5. The semicolon is his tool for balanced contrast.

Three instances, all introduced by him, none present in the draft.

| drafted | his |
| --- | --- |
| "The saving tracks trims prevented, not gradient bytes discarded" | "Prevented trims explain the saving; discarded gradient bytes do not" |
| "Two are closed by construction, two are scoped to an experiment that needs hardware a simulator cannot provide." | "Two questions are closed by construction; the other two require hardware that a simulator cannot provide." |
| "The policy flattens the worst seeds and barely moves the mild ones." | "...; mild seeds barely change." |

This is the one I got wrong. A semicolon joining a positive clause to its
negated parallel is on the standard list of machine-writing tells, so I
stripped all three in a later pass. The evidence says it is his own
construction, used deliberately and repeatedly. A personal sample
outranks a generic pattern list, and it did here.

## 6. Plain transitive verbs, never placement or metaphor verbs.

Six substitutions. Out: buys, sits in, tracks, holds, runs, carries,
lands. In: explain, gain, come from, prevent, model, price, create.

| drafted | his |
| --- | --- |
| "The saving tracks the packet trims prevented" | "Packet trims prevented explain the saving" |
| "the selective-repeat arm buys 0.78 %" | "the selective-repeat arm gains 0.78 %" |
| "most of the achievable gain sits in the permissive steps" | "most achievable gain comes from permissive steps" |
| "holds to the byte in the ledger" | "tracks it to the byte" |
| "Its tail is the rate cut, not the repair." | "The rate cut creates the tail rather than the repair." |

## 7. Rhetorical closers get deleted outright.

Four instances. He ends on the fact and never on a comment about the
fact.

| drafted | his |
| --- | --- |
| "Protecting the early steps costs most of the available gain, and we should say so" | "Protecting the early steps uses most of the available gain" |
| "That last step is why we can state the scope of the claim instead of being asked for it." | "The selective-repeat result defines the claim's scope." |
| "The claim is not that the schedule is free. It is that most of the achievable gain sits in the permissive steps anyway, so a schedule buys the early phase back cheaply." | "The schedule costs capacity, but most achievable gain comes from permissive steps, so it restores the early phase cheaply." |

No "the point is", no "we would rather", no "and that is what makes it",
no sentence whose subject is the previous sentence.

## 8. "Rather than", never "not X but Y".

He removed the one bare "not Y" construction in the draft and never
writes one. Contrast is carried by *rather than*, *while*, or the
semicolon in invariant 5.

## 9. Event labels start with their verb.

Three instances, in the timeline.

| drafted | his |
| --- | --- |
| "trimming to UEC 1.0.3" | "add trimming to UEC 1.0.3" |
| "critical-step schedule pinned" | "pin the critical-step schedule" |
| "DCQCN and forgiveness" | "add DCQCN and forgiveness" |

Nouns and passives both become active verb phrases.

## 10. Precision beats smoothness.

He keeps a clumsy construction if it is exact. "Relief drops from 3.9 to
11.1 % to 0.78 %" has two prepositions doing different jobs and he kept
it, because collapsing it would have lost the range. Do not smooth at the
cost of a number's meaning.

## 11. Repeat a number when it scopes the local claim.

State a denominator, sample size, or condition where the reader needs it
to interpret the sentence or figure in front of them. Do not make them
recover that context from an earlier slide. Remove repetitions that add no
new scope.

| drafted | his |
| --- | --- |
| "Thirteen seeds beat the baseline" | "Thirteen of 16 seeds beat the baseline" |
| "16 seeds, go-back-N" in a timeline after the result stated the sample size | "go-back-N seed study" |

## Smaller habits, single instances each

- Possessive to compress: "The four open questions from May" became
  "May's four open questions".
- Adverbs cut when the verb already carries them: "deliberately separate
  from compression" became "separately from compression".
- Colons are allowed for elaboration ("a second uncontrolled lossy layer:
  the optimiser's residual does not know...") but not for a clever
  two-part title.
- No em dash or en dash appears anywhere in his writing.
- Repeat a number when it scopes the local claim; otherwise omit it.

## Checklist before anything ships under his name

- Every sentence has a subject and a finite verb.
- The agent is the subject; no clefts, no "This is the X that".
- No staccato pair where a subordinated clause would do.
- Conditions front, claims after.
- No buys, sits, tracks, carries, holds, lands.
- Nothing after the last fact.
- Contrast uses a semicolon or "rather than".
- No dashes.
