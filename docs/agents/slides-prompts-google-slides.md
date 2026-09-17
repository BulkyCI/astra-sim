Build a complete nine-slide presentation from the specification below.

Build every slide in one pass, in order, without stopping. Do not ask
clarifying questions, do not summarise the specification back, and do not
wait for confirmation between slides. Everything you need is here: every
headline, every data point, every layout instruction. Where the spec
gives exact text in quotation marks, use that text verbatim.

Deliverable: one 16:9 presentation, 1920 x 1080 px, titled "Phase-aware
bounded loss at modern ML training scale", with speaker notes filled in
where the spec provides them.

===============================================================
DESIGN SYSTEM
===============================================================

Use these tokens on every slide. Introduce no other colour, typeface, or
decorative element.

COLOURS, two only:
  ink     #141413   all text, all rules, all chart marks, dark panels
  paper   #faf9f5   all backgrounds, and all text placed on ink panels
  Pure white #ffffff only for text on an ink panel where paper reads too
  warm.

The palette has no accent colour. Encode every chart distinction with an
ink opacity ramp, never with hue:
  ink-100   #141413 at 100%    the series being argued for
  ink-55    #141413 at 55%     the comparison series
  ink-30    #141413 at 30%     context, baselines, secondary marks
  ink-12    #141413 at 12%     gridlines, fills, shaded bands
On ink panels, use the mirror image: paper at 100%, 70%, 40%, 20%.

TYPE: "Anthropic Sans", falling back to Arial, sans-serif. Monospace runs
use "Anthropic Mono", falling back to Arial. The brand's body size is
12px for a web page; this deck is projected, so the ramp below is the
brand scale multiplied by 1.6, keeping its proportions and tracking.
  slide title      58px, weight 700, line-height 1.1
  assertion line   34px, weight 700, line-height 1.15
  section label    16px, weight 700, letter-spacing 1.2px, UPPERCASE
  body             20px, weight 400, line-height 1.4, letter-spacing -0.24px
  chart label      16px, weight 400
  figure number    28px, weight 700, monospace
  footnote         14px, weight 400, ink at 55%

SPACING: use only 2, 4, 8, 12, 16, 22, 58 and 68 px. Slide margin 68px on
all four sides. Headline to content 22px. Between columns 58px.

CORNERS: 8px on small chips, 16px on cards, 24px on full panels.

SHADOWS: barely visible. rgba(0,0,0,0.01) 0 2px 2px, rgba(0,0,0,0.02)
0 4px 4px, rgba(0,0,0,0.04) 0 16px 24px. Never heavier, never a glow,
never a gradient.

===============================================================
RULES FOR EVERY SLIDE
===============================================================

1. Headlines are plain declarative sentences. Subject first, active verb,
   no rhetorical flourish, no colon splitting a clever phrase in two.
2. Exactly one visual per slide, occupying at least half the slide.
3. At most three supporting facts, one line each. Never a bullet list
   longer than three items. Never a paragraph of body text.
4. One closing line at the bottom of the slide in ink at 55%. Give it no
   label; just place it.
5. Numbers are the hero. Any headline figure is set at 58px weight 700
   and given white space around it. Never bury a number inside a sentence
   when it can stand alone.
6. Forbidden everywhere: clip art, icons, stock photography, emoji, 3D
   effects, drop shadows on text, gradients, and pill-shaped callouts
   other than the status chips specified on slide 9.
7. Charts carry no chart junk: no legend boxes, no axis borders on all
   four sides, no data labels on every point. Label each series directly
   beside its own line or bar.
8. Slide numbers bottom right, 14px, ink at 30%, on slides 2 through 9
   only.
9. The audience did not run these experiments. Every axis, series name and
   label must be readable without that context, so name the quantity in
   plain words and give its units. Where a chart shows a large multiplier,
   put one sentence beneath it saying in words what the multiplier means.
   Do not use the words trim ratio, arm, cell, span, window, episode,
   regime or drain as labels without saying what they are.

===============================================================
SLIDE 1 of 9
===============================================================

LAYOUT: full-bleed ink panel (#141413). All text in paper (#faf9f5). No
slide number.

TITLE, 58px bold, upper left at the 68px margin, on two lines:
  "Phase-aware bounded loss"
  "at modern ML training scale"

SUBTITLE, directly beneath, 34px weight 400, paper at 70%:
  "We simulate a 64-rank lossy training fabric in ASTRA-sim/ns-3"

BOTTOM LEFT, 20px, three tight lines:
  "Joe Fang, in collaboration with Zechen Ma"
  "Progress review for Yashar Ganjali and Zechen Ma"
  "18 September 2026"

BOTTOM RIGHT, a horizontal strip of three statistics, each a figure above
a label, 58px bold figure and 16px label, 58px apart:
  "3.91 %"  above  "faster 20-step run"
  "153 ms"  above  "reduction in the slowest all-reduce"
  "0.93"    above  "correlation with prevented trims"

Nothing else. No logo, no decorative rule.

SPEAKER NOTE: "This is the revision of our own DBLP work. Everything here
is simulation on a fabric we built. Nothing here speaks to accuracy."

===============================================================
SLIDE 2 of 9
===============================================================

This slide states the motivation for the whole deck. Each card names a
gap between DBLP's evaluation and a modern fabric, and the change that
closed it. The cards read left to right as one argument.

HEADLINE, 34px bold:
  "DBLP's testbed did not resemble a modern training network"

VISUAL: five cards in one horizontal row, equal width, 16px radius, 1px
ink border, paper fill, connected left to right by 2px ink-30 arrows
placed in the gaps. Each card shows a monospace step number at 28px in
ink-30 at its top left, then a bold 20px line, then 20px body.

  Card 01, "DBLP's evaluation":
    "DBLP combines Accordion's phase awareness with lossy transport. It
    ran on 4 nodes with hand-injected loss."

  Card 02, "A lossy fabric":
    "Hand-injected loss cannot model a 64-rank fabric. ASTRA-sim's ns-3
    patch ships a lossless RDMA fabric by default, so we disabled PFC,
    added UEC packet trimming, and added selective repeat at 64 ranks."

  Card 03, "Paired comparisons":
    "Each pair shares a seed and random stream; ephemeral GitHub Actions
    runners on DCS archive both results."

  Card 04, "3.91 % lower training time":
    "Across 16 seeds, prevented trims explain the 3.91 % reduction, and
    selective repeat limits it."

  Card 05, "DBLP under congestion control":
    "FORGIVE lets DBLP run under congestion control: the receiver
    accepts trimmed loss, counts the budget in bytes, and withdraws a
    sender's exemption once that budget is spent."

CLOSING LINE, centred beneath the row:
  "The simulation includes fabric loss, 64 ranks, and congestion control."

SPEAKER NOTE: "We could not trust a result until the environment
resembled a real fabric, so the order of these cards is the order the
work had to happen in. Nothing here was exploratory; each run had a
decision rule written before it was dispatched, and the rule chose the
next run."

===============================================================
SLIDE 3 of 9
===============================================================

Each band names a model dependency, not an implementation task.

HEADLINE, 34px bold:
  "The simulator models loss and recovery before it measures DBLP"

VISUAL: a horizontal timeline spanning the full content width. The axis
is a 2px ink rule with ticks at 20 July, 31 July, 11 August, 22 August,
1 September and 16 September, labelled at 16px beneath.

ABOVE THE AXIS: four stacked bands, each an ink-12 rectangle with a 1px
ink-30 border, 24px tall, labelled inside at 16px bold, spanning:
  "Model packet loss and recovery"      20 Jul to 11 Aug
  "Pair runs deterministically"          9 Aug to  1 Sep
  "Measure seed-dependent effects"       1 Sep to  7 Sep
  "Model congestion control"             5 Sep to 16 Sep

BETWEEN BANDS AND AXIS: small ink dots on the axis with 16px labels
above, joined by 1px ink-30 leader lines:
  20 Jul  "fork ASTRA-sim"
  27 Jul  "add UEC packet trimming"
   4 Aug  "add trimming to UEC 1.0.3"
   6 Aug  "add selective repeat"
  9 Aug  "provision DCS GitHub Actions runners"
  17 Aug  "pin the protected-step schedule"
  22 Aug  "choose seeds"
   5 Sep  "add DCQCN and FORGIVE"
  14 Sep  "revoke the exemption on a spent budget"

BELOW THE AXIS: four solid ink diamonds on 2px ink stems, each with a
bold 20px label and a 16px sublabel:
  1 Sep  "16 paired seeds"  /  "go-back-N recovery"
  6 Sep  "8 configurations"  /  "selective repeat"
  14 Sep  "FORGIVE"  /  "3 seeds, 1 fabric, 1 controller"
  16 Sep  "Paced forgiveness"  /  "training time and gradient loss"

CLOSING LINE:
  "Shared seeds and random streams let paired run times be subtracted."

SPEAKER NOTE: "ASTRA-sim's ns-3 patch defaults to lossless RoCEv2. Turning off PFC
and adding trimming is one change, from lossless RDMA to lossy RDMA, and
it is the change the whole question depends on. Selective repeat came
after, and it is what slide 6 turns out to be about. Each paired result
shares a seed and a random stream, and a comparison runs for about five
hours on a runner minted for that job."

===============================================================
SLIDE 4 of 9
===============================================================

The main result. The chart is the slide.

HEADLINE, 34px bold:
  "DBLP reduces 20-step time in 13/16 seeds"

VISUAL: horizontal dumbbell chart across the left two thirds. One row per
seed, sorted by relief descending. Horizontal axis is the 20-step
training window in milliseconds, labelled "Time to finish 20 training
steps (ms)", with ticks at 6500, 6700, 6900, 7100, 7300, 7500, 7700 and
7850, gridlines ink-12. Each row: an ink-30 filled
circle at the baseline value and an ink-100 filled circle at the policy
value, joined by a 3px line. On the three rows where the policy is worse,
draw the joining line in ink-55 instead. Seed labels at 16px on the left,
relief percentage at 16px on the right.

DATA, seed / baseline ms / policy ms / relief %:
  53589793  7526.6  6646.6  +11.69
  16939937  7400.5  6649.0  +10.15
  74944592  7723.0  7003.8   +9.31
  62862089  7268.5  6692.9   +7.92
  98628034  7414.9  6858.9   +7.50
  48086513  7192.9  6816.3   +5.23
  30781640  6995.2  6710.4   +4.07
  23846264  7011.9  6727.2   +4.06
  70938446  7376.3  7087.6   +3.91
  82534211  6834.8  6583.8   +3.67
   2884197  7333.6  7071.3   +3.58
  28230664  7079.6  6847.0   +3.29
  51058209  6856.9  6691.8   +2.41
  33832795  6872.0  6969.6   -1.42
  31415926  6800.6  7170.3   -5.44
  70679821  6634.4  7128.8   -7.45

DIRECT LABELS beside the first row, no legend box:
  ink-30 circle    "Baseline"  /  "0.5 % loss on every step"
  ink-100 circle   "DBLP"  /  "0.5 % on steps 1, 2, 3, 20; 10 % elsewhere"

RIGHT THIRD: an ink panel, 24px radius, paper text:
  section label  "PAIRED RUNS"
  "3.91 %" at 58px bold
  "faster 20-step run, 95 % CI [1.13, 6.68] %" at 16px
  a 1px paper-30 divider
  "153 ms" at 58px bold
  "reduction in the slowest all-reduce, CI [5, 302] ms" at 16px

CLOSING LINE:
  "On the 4 seeds whose slowest all-reduce exceeds 1.3 s, DBLP cuts that
  all-reduce by 434 to 716 ms; on 3 seeds, it raises 20-step time by
  1.42 to 7.45 %."

SPEAKER NOTE: "Seeds are eight-digit chunks of pi, fixed before the run.
The two runs share one random stream, so the messages the baseline drops
are exactly the ones the policy considers. Quote the slowest all-reduce
as 153 ms, never as a percentage."

===============================================================
SLIDE 5 of 9
===============================================================

Two scatter panels side by side, equal width, sharing one vertical axis
label.

HEADLINE, 34px bold, two sentences:
  "Prevented trims predict 20-step savings; discarded gradient bytes do not."

GLOSS LINE directly beneath the headline, 16px, ink at 55%:
  "During a trim, a switch drops packet payload and forwards the header."

SHARED VERTICAL AXIS, labelled "20-step savings (ms)",
ticks at
-600, -300, 0, 300, 600 and 900, gridlines ink-12, a heavier ink-30 line
at zero.

LEFT PANEL, titled "Savings versus prevented trims". Marks in
ink-100 with a dashed ink-55 least-squares line. Horizontal axis "Packet
trims prevented (millions)", ticks at -40, -20, 0, 20, 40, 60 and 80.
Place "r = 0.93" at 58px bold inside the panel, upper left, with generous
space around it.

RIGHT PANEL, titled "Savings versus discarded gradient bytes". Marks in ink-55,
no fit line. Horizontal axis "Discarded gradient bytes (GB)", ticks at
1.85, 1.95, 2.05, 2.15, 2.25, 2.35 and 2.45. Place "r = -0.01" at 58px
bold inside the panel, upper left.

DATA, ms saved / trims prevented in millions / GB discarded:
   880.0   76.17  2.19
   751.5   40.62  2.14
   719.2   55.17  1.97
   575.6   36.38  2.10
   556.0   32.90  2.35
   376.6   37.12  2.10
   288.7   21.18  1.99
   284.8   27.82  2.20
   284.7   24.39  2.25
   262.3    4.54  2.15
   251.0   46.34  2.23
   232.6   20.19  2.03
   165.1   14.15  1.95
   -97.6   -3.27  1.93
  -369.7  -37.54  2.36
  -494.4  -32.91  2.10

THREE SUPPORTING LINES beneath the panels, 20px, no bullets, 22px apart:
  "Each seed discards 1.93 to 2.36 GB, but that does not predict 20-step savings."
  "The slope is 11.9 ms per million trims prevented."
  "The policy regresses on the 3 seeds where it adds trims."

CLOSING LINE:
  "With go-back-N, discarding 1.98 GiB of gradient removes 156 GiB from the
  wire because a trimmed packet rewinds a whole window."

SPEAKER NOTE: "This is what makes the result an explanation rather than a
percentage, and it is what told us where the gain would not appear, which
is the next slide."

===============================================================
SLIDE 6 of 9
===============================================================

This slide states the scope of the result. Selective repeat was our own
fidelity change, so the limit comes from the same programme as the gain.
The slide must not read as an apology.

HEADLINE, 34px bold:
  "DBLP saves 0.78 % with selective repeat, versus 3.9 to 11.1 % with go-back-N"

VISUAL: horizontal bar chart on a logarithmic axis from 1x to 1000x
across the left two thirds, titled "Go-back-N overhead versus selective
repeat under the same workload and burst". One bar
per measure, ink-100 fill, drawn as a range from its low value to its
high value, with the low and high multiplier printed at the bar's two
ends. Gridlines at 1x, 10x, 100x and 1000x in ink-12, labelled at 16px.

Measure names on the left at 16px, with the two underlying values in
ink-55 at 14px on a second line. Each second line names both schemes, so
nobody has to guess which number belongs to which:

  "Switch-trimmed bytes / offered byte"             110x to 520x
      "go-back-N 2.2 to 10.4    selective repeat 0.02"
  "Retransmitted bytes / offered byte"               54x to 312x
      "go-back-N 7 to 25    selective repeat 0.08 to 0.13"
  "Time to clear a 7-sender burst"                   15x to  78x
      "go-back-N 423 to 1798 ms    selective repeat 23 to 29 ms"
  "All-reduce time, burst step"                      12x to  53x
      "go-back-N 205 to 935 ms    selective repeat 17.6 ms"
  "20-step run time"                                3.7x to 5.6x
      "go-back-N 4503 to 6795 ms    selective repeat 1210 ms"

READING LINE directly beneath the chart, 16px, ink at 55%:
  "At equal workload, go-back-N creates 110 to 520x as many trimmed bytes
  as selective repeat."

SUPPORTING LINE beneath the reading line, 20px:
  "Selective repeat retransmits lost packets without rewinding the window."

RIGHT THIRD: an ink panel with paper text:
  section label  "NETWORK SWEEP"
  "8 configurations" at 34px bold
  "Across 64 ranks with selective repeat, the sweep varies congestion
  control, fan-in, and spine oversubscription."
  a 1px paper-30 divider
  "We required switches to trim at least 0.5 bytes per byte sent. The
  most congested configuration reached 0.24."
  "We required the 7-sender burst to take at least 20 % of training time. The
  most congested configuration reached 0.62 %."

CLOSING LINE, two sentences:
  "DBLP saves 3.9 to 11.1 % with go-back-N, while it saves 0.78 % with
  selective repeat. All bounded-loss results in our review use
  go-back-N-like recovery."

SPEAKER NOTE: "Do not let this land as a caveat. The field is moving to
selective repeat and Ultra Ethernet, so the finding that admission-time
tolerance loses most of its value in that move is worth knowing on its
own, and it is what motivated the mechanism on the next slide."

===============================================================
SLIDE 7 of 9
===============================================================

The mechanism, and the whole protocol in three facts. Every modern fabric
runs congestion control, so DBLP has to work under one.

HEADLINE, 34px bold:
  "FORGIVE lets a sender ignore congestion control while the receiver
  still has loss budget"

VISUAL, occupying the left two thirds: three boxes left to right, equal
size, 16px radius, 1px ink border, paper fill, labelled at 20px bold
"Sender NIC", "Switch" and "Receiver NIC". A 3px ink-100 arrow runs left
to right beneath the boxes, labelled at 16px "gradient data". Above the
switch, a 2px ink-55 arrow turns down and stops, labelled "the switch
drops the payload and forwards the header". Two 2px ink-30 arrows return
right to left from the receiver to the sender, labelled at 16px:
  "repair this range"
  "this range is forgiven, and you may ignore rate cuts"

THREE SUPPORTING LINES on the right third, 20px, each with its key phrase
at 34px bold on its own line above 20px body:

  "one budget per rank per step"
  "Each receiving rank may forgive a fraction p of the bytes that step
  owes it, pooled across every sender into that rank."

  "a coin at probability P"
  "The receiver forgives a trimmed range when the coin says yes and the
  bytes already delivered have earned the allowance, and asks for the
  repair otherwise."

  "two bits, and nothing new on the wire"
  "The receiver withdraws the exemption with one bit once the budget is
  spent, and the sender obeys its controller for the rest of the step."

CLOSING LINE:
  "Every rank is certified after every step to have received at least
  1 - p of what it was owed, and a run that breaks that certificate
  fails."

SPEAKER NOTE: "The time comes from how long a sender may ignore the
congestion controller; forgiveness is the currency that licenses it, and
the coin spends that currency slowly, so the licence lasts the whole step
at almost no loss. The receiver also stops a sender the moment 1 - p of
that sender's share for the step has arrived. On the application side we
assume the framework divides each reduce-scatter element by the
contributions that arrived; the conservative bound for that assumption is
our own May GPT-2 runs, which survived 40 % with no rescale at all."

===============================================================
SLIDE 8 of 9
===============================================================

The numbers. Mark them preliminary in the visual itself, not only in the
notes.

HEADLINE, 34px bold:
  "Pacing the forgiveness recovers 16 % of training time for 1.3 % of
  gradient bytes"

VISUAL, occupying the left two thirds: a scatter chart with three
connected series, under a section label reading "PRELIMINARY: 3 SEEDS,
1 FABRIC, 1 CONGESTION CONTROLLER". Horizontal axis "Gradient bytes
discarded (% of all data-parallel bytes)", ticks at 0, 10, 20, 30, 40 and
50. Vertical axis "Training time recovered (%)", ticks at 0, 4, 8, 12,
16, 20 and 24. Shade the band from 0.7 % to 3.3 % in ink-12, labelled at
14px "MLT (NSDI 2024) reports models tolerating 0.7 % to 3.3 %".

  Series A, ink-100, solid line with filled circles, labelled directly
  "FORGIVE with the coin, budget 0.1", points as (x, y), one per coin
  probability, 0.05 then 0.1 then 0.25:
    (1.3, 15.9)   (2.7, 16.0)   (5.7, 16.1)

  Series B, ink-55, solid line with filled circles, labelled directly
  "FORGIVE without the coin, budget 0.05 to 0.6", points as (x, y):
    (3.8, 8.3)   (6.8, 13.4)   (11.7, 16.5)   (21.5, 20.3)   (38.1, 24.0)

  Series C, ink-30, solid line with hollow circles, labelled directly
  "Sender drop", points as (x, y):
    (7.7, 2.9)   (15.7, 5.3)   (31.5, 11.4)   (47.9, 16.2)

READING LINE directly beneath the chart, 16px, ink at 55%:
  "Further right means more gradient thrown away and higher means more
  training time recovered, so the coin moves the operating point left at
  the same height."

THREE SUPPORTING LINES on the right third, 20px, each with its key figure
at 34px bold on its own line above 20px body:

  "4x less loss"
  "Between a coin of 0.25 and a coin of 0.05 the gradient loss falls by a
  factor of 4 and the training time recovered stays inside the spread
  across seeds."

  "-1.1 to +0.8 %"
  "An arm that tolerates no loss at all reads within this band of our
  baseline over 5 seeds, so every number here stands against DCQCN with
  no loss tolerance."

  "5.5 to 6.6 % against 20.1 to 20.3 %"
  "Forgiveness that obeys the controller recovers the first figure;
  turning the controller off entirely recovers the second and puts 25.4 %
  of every byte back on the wire as repairs."

CLOSING LINE:
  "Run #127 measures the whole design on the cluster tonight, and no
  number on this slide comes from it."

SPEAKER NOTE: "The headline candidate is a coin of 0.05 at a budget of
0.1: about 16 % of training time for 1.2 to 1.3 % of gradient bytes,
which is inside the band MLT profiles as tolerable, against our own May
GPT-2 runs surviving 40 %. Without the coin the same budget costs 6.75 to
6.89 % of gradient bytes for 12.9 to 14.1 % of the time, and lowering the
budget to 0.05 instead recovers only 8.0 to 8.6 % for 3.74 to 3.77 %. The
mechanism is in the exemption: at a coin of 0.1 and 0.05 all but 3 exempt
flows of 71 680 keep their exemption for the whole step, against 35 to
37 % losing it without the coin. Run #127 runs 21 arms at budget 0.1 on
the design of record and its ablations, read with the tensor-parallel
all-reduce span and re-sent bytes against the baseline, which is how we
price what an exempt sender costs the rest of the fabric."

===============================================================
SLIDE 9 of 9
===============================================================

HEADLINE, 34px bold:
  "The study answers 2 July questions; 2 require hardware"

VISUAL: a two-by-two grid of cards, 16px radius, 1px ink border, paper
fill, equal size, 22px gutter. Each card shows a monospace number at
28px in ink-30, a bold 20px question, and 20px body. Put a status chip in
each card's top right: 8px radius, ink-100 fill, paper text, 14px,
reading either "CLOSED" or "SCOPED".

  Card 01, chip "SCOPED", question "Sparsification":
    "We model pure drop without error feedback, separately from
    compression. Mixing them creates a second uncontrolled lossy layer."

  Card 02, chip "CLOSED", question "Compute and transport interleaving":
    "Chakra traces show 5.4 ms of compute per node overlapping the run, so
    the study reports exposed communication time rather than end-to-end
    training time."

  Card 03, chip "SCOPED", question "CLR identification":
    "The simulator has no gradients, so it cannot host a detector. The
    schedule is pinned from CLR detection literature."

  Card 04, chip "CLOSED", question "Centralized traffic versus ring traffic":
    "Fan-in multiplies switch trimming 2.7x, while spine oversubscription
    multiplies it 5.5x. At 7:1, fan-in creates the study's highest switch
    trimming at one NIC."

CLOSING LINE:
  "The remaining 2 questions require hardware rather than a simulator."

===============================================================
FINAL CHECK BEFORE YOU FINISH
===============================================================

Verify each of these across the finished deck, and fix anything that
fails rather than reporting it:

  Nine slides exist, no more and no fewer.
  Slide 1 is a full-bleed ink panel; the rest are paper.
  Every headline is a plain declarative sentence with an active verb.
  Every slide except 1 has exactly one visual and one closing line in ink
    at 55%.
  No slide shows more than three supporting facts.
  Only #141413 and #faf9f5 appear, plus opacity steps of the two.
  No icons, emoji, clip art, gradients, or text shadows anywhere.
  Every chart series is labelled beside itself, with no legend box.
  Every number in the deck matches the specification digit for digit.
  Speaker notes are attached wherever the specification supplied one.

The through-line, in case a headline needs rewording. DBLP ran on 4 nodes
with hand-injected loss, which does not model a modern training fabric.
ASTRA-sim's ns-3 patch ships a lossless RDMA fabric by default; the
simulation converts it to a lossy fabric by disabling PFC and adding UEC
packet trimming. Selective repeat matches modern recovery, and the
simulation runs at 64 ranks. Each paired result shares a seed and random
stream, and ephemeral DCS runners archive both results. Selective repeat
reduces DBLP's 3.9 to 11.1 % go-back-N relief to 0.78 %, which defines the
result's scope. FORGIVE applies DBLP under congestion control, and pacing
its forgiveness with a coin recovers about 16 % of training time for 1.2
to 1.3 % of gradient bytes.

Context, in case a caption needs it. The numbers come from eight cluster
runs of an ASTRA-sim and ns-3 simulation on a University of Toronto
cluster, between 1 and 16 September 2026. Each result is a pair of
simulated runs that share a seed and a random stream, so their times can
be subtracted. Trimming is a switch discarding a packet's payload and
forwarding its header, which is how this fabric signals congestion.
Go-back-N makes a sender re-send everything from the lost packet onward;
selective repeat re-sends only what was lost. The audience did not run
any of this, so prefer a plain description over the project's shorthand
in anything visible on a slide.
