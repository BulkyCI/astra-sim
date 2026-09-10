Build a complete eight-slide presentation from the specification below.

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
   other than the status chips specified on slide 8.
7. Charts carry no chart junk: no legend boxes, no axis borders on all
   four sides, no data labels on every point. Label each series directly
   beside its own line or bar.
8. Slide numbers bottom right, 14px, ink at 30%, on slides 2 through 8
   only.

===============================================================
SLIDE 1 of 8
===============================================================

LAYOUT: full-bleed ink panel (#141413). All text in paper (#faf9f5). No
slide number.

TITLE, 58px bold, upper left at the 68px margin, on two lines:
  "Phase-aware bounded loss"
  "at modern ML training scale"

SUBTITLE, directly beneath, 34px weight 400, paper at 70%:
  "Benefits and limits, measured in ASTRA-sim and ns-3"

BOTTOM LEFT, 20px, three tight lines:
  "Joe Fang, in collaboration with Zechen Ma"
  "Progress review for Yashar Ganjali"
  "9 September 2026"

BOTTOM RIGHT, a horizontal strip of three statistics, each a figure above
a label, 58px bold figure and 16px label, 58px apart:
  "3.91 %"  above  "shorter training window"
  "153 ms"  above  "off the episode's worst all-reduce"
  "0.93"    above  "correlation with trims prevented"

Nothing else. No logo, no decorative rule.

SPEAKER NOTE: "This is the revision of our own DBLP work. Everything here
is simulation on a fabric we built. Nothing here speaks to accuracy."

===============================================================
SLIDE 2 of 8
===============================================================

This slide carries the motivation for everything that follows. The cards
must read left to right as one argument, each one explaining why the next
piece of work existed.

HEADLINE, 34px bold:
  "We set out to test the DBLP idea on a fabric that behaves like the
  real thing"

VISUAL: five cards in one horizontal row, equal width, 16px radius, 1px
ink border, paper fill, connected left to right by 2px ink-30 arrows
placed in the gaps. Each card carries a monospace step number at 28px in
ink-30 at its top left, then a bold 20px line, then 20px body.

  Card 01, "The idea":
    "DBLP combines Accordion's phase awareness with a lossy transport. On
    four nodes, with loss we injected by hand, it worked."

  Card 02, "Make the loss real":
    "Injected loss says nothing about a real fabric. The ns-3 backend
    ships lossless RDMA, so we made it lossy: PFC off plus UEC packet
    trimming. We then added selective repeat, because that is how modern
    transports recover."

  Card 03, "Make the experiment survivable":
    "A single comparison occupies the cluster for most of a day. A month
    went into the harness, matched arms, sixteen seeds and permanent
    artifacts before any result was worth reading."

  Card 04, "What the fabric said":
    "Training time fell 3.91 % across sixteen seeds. The saving tracks
    the packet trims we prevented, and the recovery scheme sets its
    limit."

  Card 05, "What the idea should become":
    "FORGIVE is what DBLP looks like once the fabric runs congestion
    control. The receiver decides, the budget is a ledger, and the
    exemption revokes itself."

CLOSING LINE, centred beneath the row:
  "We built each piece because the idea could not be tested without it."

SPEAKER NOTE: "Nothing here was exploratory. Each run had a decision rule
written before it was dispatched, and the rule chose the next run."

===============================================================
SLIDE 3 of 8
===============================================================

HEADLINE, 34px bold:
  "What we built, and what we ran"

VISUAL: a horizontal timeline spanning the full content width. The axis
is a 2px ink rule with ticks at 20 July, 31 July, 11 August, 22 August,
1 September and 9 September, labelled at 16px beneath.

ABOVE THE AXIS: four stacked bands, each an ink-12 rectangle with a 1px
ink-30 border, 24px tall, labelled inside at 16px bold, spanning:
  "Build the instrument"            20 Jul to 11 Aug
  "Make it an experiment platform"   9 Aug to  1 Sep
  "Map the regime"                   1 Sep to  7 Sep
  "FORGIVE"                          5 Sep to  9 Sep

BETWEEN BANDS AND AXIS: small ink dots on the axis with 16px labels
above, joined by 1px ink-30 leader lines:
  20 Jul  "fork ASTRA-sim"
  27 Jul  "UEC packet trimming"
   4 Aug  "add trimming to UEC 1.0.3"
   6 Aug  "selective repeat"
   9 Aug  "SLURM cluster runners"
  17 Aug  "pin critical-step schedule"
  22 Aug  "sixteen seeds"
   5 Sep  "add DCQCN and forgiveness"

BELOW THE AXIS: four solid ink diamonds on 2px ink stems, each with a
bold 20px label and a 16px sublabel:
   1 Sep  "run #117"  /  "16 seeds, go-back-N"
   6 Sep  "run #120"  /  "8-cell regime map"
   7 Sep  "run #121"  /  "FORGIVE"
   8 Sep  "run #122"  /  "budget sweep"

CLOSING LINE:
  "One comparison occupies the cluster for most of a day and a full run
  for several, which is why a month went into the harness: 184 commits,
  four cluster jobs, about 180 simulated configurations."

SPEAKER NOTE: "The stock ns-3 backend is lossless RoCEv2. Turning off PFC
and adding trimming is one change, from lossless RDMA to lossy RDMA, and
it is the change the whole question depends on. Selective repeat came
after, and it is what slide 6 turns out to be about. I did not expect the
second band to take a month, but a comparison that runs for a day is only
useful if it survives the runner dying halfway through."

===============================================================
SLIDE 4 of 8
===============================================================

The main result. The chart is the slide.

HEADLINE, 34px bold:
  "Thirteen of sixteen seeds improved on the baseline"

VISUAL: horizontal dumbbell chart across the left two thirds. One row per
seed, sorted by relief descending. Horizontal axis is the 20-step
training window in milliseconds, with ticks at 6500, 6700, 6900, 7100,
7300, 7500, 7700 and 7850, gridlines ink-12. Each row: an ink-30 filled
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
  ink-100 circle   "Policy"    /  "0.5 % on steps 1, 2, 3, 20 and 10 % elsewhere"

RIGHT THIRD: an ink panel, 24px radius, paper text:
  section label  "PAIRED, N = 16"
  "3.91 %" at 58px bold
  "shorter training window, 95 % CI [1.13, 6.68] %" at 16px
  a 1px paper-30 divider
  "153 ms" at 58px bold
  "off the worst all-reduce of the episode, CI [5, 302] ms" at 16px

CLOSING LINE:
  "On the four seeds whose worst all-reduce exceeds 1.3 s, the policy
  cuts that collective by 434 to 716 ms. The mild seeds barely move."

SPEAKER NOTE: "Seeds are eight-digit chunks of pi, fixed before the run.
Arms are matched off one random selection stream, so the messages the
baseline suppresses are exactly the ones the policy considers. Quote the
worst all-reduce as 153 ms, never as a percentage."

===============================================================
SLIDE 5 of 8
===============================================================

Two scatter panels side by side, equal width, sharing one vertical axis
label.

HEADLINE, 34px bold, two sentences:
  "Trims prevented predict the saving. Bytes discarded predict nothing."

SHARED VERTICAL AXIS, labelled "Milliseconds saved on window", ticks at
-600, -300, 0, 300, 600 and 900, gridlines ink-12, a heavier ink-30 line
at zero.

LEFT PANEL, titled "Packet trims prevented by the policy". Marks in
ink-100 with a dashed ink-55 least-squares line. Horizontal axis "Packet
trims prevented (millions)", ticks at -40, -20, 0, 20, 40, 60 and 80.
Place "r = 0.93" at 58px bold inside the panel, upper left, with generous
space around it.

RIGHT PANEL, titled "Against gradient bytes discarded". Marks in ink-55,
no fit line. Horizontal axis "Gradient bytes discarded (GB)", ticks at
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
  "Each seed discards about the same two gigabytes, which predicts
  nothing."
  "The slope is 11.9 ms per million trims prevented."
  "The policy regresses on the three seeds where it adds trims."

CLOSING LINE:
  "Under go-back-N, discarding 1.98 GiB of gradient removed 156 GiB from
  the wire, because one trimmed packet rewinds a whole window."

SPEAKER NOTE: "This is what makes the result an explanation rather than a
percentage, and it is what told us where the gain would not appear, which
is the next slide."

===============================================================
SLIDE 6 of 8
===============================================================

This slide states the scope of the result. It must not read as an
apology.

HEADLINE, 34px bold:
  "The gain comes from go-back-N, and selective repeat removes it"

VISUAL: horizontal bar chart on a logarithmic axis from 1x to 1000x
across the left two thirds, titled "Cost ratio, go-back-N over selective
repeat". One bar per metric, ink-100 fill, drawn as a range from its low
value to its high value, with the low and high multiplier printed at the
bar's two ends. Gridlines at 1x, 10x, 100x and 1000x in ink-12, labelled
at 16px.

Metric labels on the left at 16px, with the underlying pair in ink-55 at
14px on a second line:
  "trim ratio"                      110x to 520x
      "2.2 to 10.4 against 0.02"
  "retransmitted per offered byte"   54x to 312x
      "7x to 25x against 0.08x to 0.13x"
  "burst drain time"                 15x to  78x
      "423 to 1798 ms against 23 to 29 ms"
  "all-reduce span, burst step"      12x to  53x
      "205 to 935 ms against 17.6 ms"
  "20-step window"                  3.7x to 5.6x
      "4503 to 6795 ms against 1210 ms"

RIGHT THIRD: an ink panel with paper text:
  section label  "WE MAPPED THE REGIME"
  "8 cells" at 34px bold
  "Across 64 ranks with selective repeat, we varied congestion control,
  fan-in and oversubscription under a rule written before the run."
  a 1px paper-30 divider
  section label  "TRIM RATIO RULE"
  "The rule required 0.5. The worst cell reached 0.24."
  section label  "BURST EXCESS RULE"
  "The rule required 20 % of the window. The worst cell reached 0.62 %."

CLOSING LINE, two sentences:
  "Relief across our go-back-N arms is 3.9 to 11.1 %, while the
  selective-repeat arm gains 0.78 %. Our literature review found every
  bounded-loss result, ours included, measured on a transport that
  recovers the way go-back-N does."

SPEAKER NOTE: "Do not let this land as a caveat. The field is moving to
selective repeat and Ultra Ethernet, so the finding that admission-time
tolerance loses most of its value in that move is worth knowing on its
own, and it is what motivated the mechanism on the next slide."

===============================================================
SLIDE 7 of 8
===============================================================

Future work. Mark it preliminary in the visual itself, not only in the
notes.

HEADLINE, 34px bold:
  "FORGIVE is the idea rebuilt for a fabric that runs congestion control"

LEFT HALF: three stacked statements, 22px apart, each with its key figure
at 34px bold on its own line above 20px body text.

  "24 %"
  "Once the transport repairs selectively, congestion control is what
  costs time. DCQCN lengthens the training window by this much on the
  worst cell of the map, while cutting packet trimming eightfold. The
  rate cut creates the tail, not the repair."

  "10.4 to 10.9 %"
  "FORGIVE recovers this by letting the receiver forgive what the fabric
  trimmed, and letting a flow with unspent budget ignore rate cuts until
  the receiver refuses it. It spends 6.3 % of data-parallel bytes."

  "4 to 5x"
  "FORGIVE recovers that much more time per unit of gradient discarded
  than sender-side shedding does, at every budget we tested."

RIGHT HALF: a scatter chart with two connected series, under a section
label reading "PRELIMINARY: THREE SEEDS, ONE CELL, ONE CONTROLLER".
Horizontal axis "Gradient bytes discarded (%)", ticks at 0, 10, 20, 30,
40 and 50. Vertical axis "Training time recovered (%)", ticks at 0, 3, 6,
9, 12, 15 and 18. Shade the band from 0.7 % to 3.3 % in ink-12, labelled
at 14px "tolerance range MLT reports (0.7 % to 3.3 %)". Draw a dashed
ink-30 vertical line at 10 %, labelled "MLT at a quality target (10 %)".

  Series A, ink-100, solid line with filled circles, labelled directly
  "FORGIVE", points as (x, y):
    (6.4, 10.6)   (8.5, 12.5)   (9.4, 13.3)   (9.2, 13.0)

  Series B, ink-55, solid line with hollow circles, labelled directly
  "Sender-side shedding", points as (x, y):
    (7.7, 2.9)   (15.7, 5.3)   (31.5, 11.4)   (47.9, 16.2)

CLOSING LINE:
  "The curve flattens above budget 0.2, and the loss stops near 9.3 %
  because the fabric stops trimming before the budget runs out."

SPEAKER NOTE: "Present this as ongoing, not as a result. The design
borrows from transports the field already trusts: the receiver drives
repair the way selective acknowledgement does, the budget is a ledger
rather than a probability, and the exemption revokes itself on the
receiver's first refusal, so it cannot outlive what justified it.
Sender-side shedding only overtakes on time past a budget of about 0.45,
where it is discarding a third of every gradient, and no published
tolerance result reaches there."

===============================================================
SLIDE 8 of 8
===============================================================

HEADLINE, 34px bold:
  "Where the four July questions stand"

VISUAL: a two-by-two grid of cards, 16px radius, 1px ink border, paper
fill, equal size, 22px gutter. Each card carries a monospace number at
28px in ink-30, a bold 20px question, and 20px body. Put a status chip in
each card's top right: 8px radius, ink-100 fill, paper text, 14px,
reading either "CLOSED" or "SCOPED".

  Card 01, chip "SCOPED", question "Sparsification":
    "We model pure drop without error feedback, kept separate from
    compression. Mixing them creates a second uncontrolled lossy layer."

  Card 02, chip "CLOSED", question "Compute and transport interleaving":
    "Chakra traces overlap 5.4 ms of compute per node with the window, so
    we report exposed communication time. That overlap is the confound
    that stops us quoting the preprint's headline number."

  Card 03, chip "SCOPED", question "CLR identification":
    "A simulator with no gradients cannot host a detector, so we pinned
    the schedule from the CLR detection literature."

  Card 04, chip "CLOSED", question "Centralized against ring":
    "We measured two axes. Fan-in and spine oversubscription set the trim
    ratio, multiplying it 2.7x and 5.5x. Our fan-in 7 cell models
    hub-and-spoke pressure at one NIC and is the worst on the map."

CLOSING LINE:
  "Two are closed by construction. The other two need hardware a
  simulator cannot provide."

===============================================================
FINAL CHECK BEFORE YOU FINISH
===============================================================

Verify each of these across the finished deck, and fix anything that
fails rather than reporting it:

  Eight slides exist, no more and no fewer.
  Slide 1 is a full-bleed ink panel; the rest are paper.
  Every headline is a plain declarative sentence with an active verb.
  Every slide except 1 has exactly one visual and one closing line in ink
    at 55%.
  No slide carries more than three supporting facts.
  Only #141413 and #faf9f5 appear, plus opacity steps of the two.
  No icons, emoji, clip art, gradients, or text shadows anywhere.
  Every chart series is labelled beside itself, with no legend box.
  Every number in the deck matches the specification digit for digit.
  Speaker notes are attached wherever the specification supplied one.

The through-line of the deck, in case a headline needs rewording: we
wanted to run the DBLP idea on an environment as close to a modern
training fabric as we could build, which is why we converted the shipped
lossless RDMA backend into a lossy one with PFC off and UEC packet
trimming, and added selective repeat on top of it; stabilising the
experiment took a month we had not planned for; and FORGIVE is the
design that idea turns into once you accept that a real fabric runs
congestion control.

Context, in case a caption needs it: the numbers come from four cluster
runs of an ASTRA-sim and ns-3 simulation on a University of Toronto
cluster, between 1 and 8 September 2026. An arm is one simulated
configuration; arms sharing a seed and a random selection stream are
compared against each other. The trim ratio is trimmed payload bytes
divided by offered bytes. The training window is wall-clock time for 20
training steps.
