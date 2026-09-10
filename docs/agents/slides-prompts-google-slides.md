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
9. The audience did not run these experiments. Every axis, series name and
   label must be readable without that context, so name the quantity in
   plain words and give its units. Where a chart shows a large multiplier,
   put one sentence beneath it saying in words what the multiplier means.
   Do not use the words trim ratio, arm, cell, span, window, episode,
   regime or drain as labels without saying what they are.

===============================================================
SLIDE 1 of 8
===============================================================

LAYOUT: full-bleed ink panel (#141413). All text in paper (#faf9f5). No
slide number.

TITLE, 58px bold, upper left at the 68px margin, on two lines:
  "Phase-aware bounded loss"
  "at modern ML training scale"

SUBTITLE, directly beneath, 34px weight 400, paper at 70%:
  "Measured benefits and limits"

BOTTOM LEFT, 20px, three tight lines:
  "Joe Fang, in collaboration with Zechen Ma"
  "Progress review for Yashar Ganjali"
  "9 September 2026"

BOTTOM RIGHT, a horizontal strip of three statistics, each a figure above
a label, 58px bold figure and 16px label, 58px apart:
  "3.91 %"  above  "faster 20-step run"
  "153 ms"  above  "reduction in the slowest all-reduce"
  "0.93"    above  "correlation with prevented trims"

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
  "We tested DBLP on a lossy fabric"

VISUAL: five cards in one horizontal row, equal width, 16px radius, 1px
ink border, paper fill, connected left to right by 2px ink-30 arrows
placed in the gaps. Each card carries a monospace step number at 28px in
ink-30 at its top left, then a bold 20px line, then 20px body.

  Card 01, "DBLP under injected loss":
    "DBLP combines Accordion's phase awareness with lossy transport. It
    worked on four nodes with hand-injected loss."

  Card 02, "Lossy fabric":
    "Injected loss does not capture fabric behavior. The ns-3 backend is lossless
    RDMA, so we turned PFC off and added UEC packet trimming and selective
    repeat."

  Card 03, "Experimental harness":
    "One paired comparison takes a day. We built a harness with
    ephemeral GitHub Actions runners on DCS and archived the results."

  Card 04, "Result":
    "Training time fell 3.91 % across 16 seeds. Trims the policy
    prevented explain the saving, and the recovery scheme limits it."

  Card 05, "FORGIVE":
    "FORGIVE adapts DBLP to congestion control. The receiver decides which
    loss to accept, counts the budget in bytes, and revokes exemptions."

CLOSING LINE, centred beneath the row:
  "Each addition was required to test DBLP."

SPEAKER NOTE: "Nothing here was exploratory. Each run had a decision rule
written before it was dispatched, and the rule chose the next run."

===============================================================
SLIDE 3 of 8
===============================================================

HEADLINE, 34px bold:
  "We built the platform and ran the experiments"

VISUAL: a horizontal timeline spanning the full content width. The axis
is a 2px ink rule with ticks at 20 July, 31 July, 11 August, 22 August,
1 September and 9 September, labelled at 16px beneath.

ABOVE THE AXIS: four stacked bands, each an ink-12 rectangle with a 1px
ink-30 border, 24px tall, labelled inside at 16px bold, spanning:
  "Build instrumentation"              20 Jul to 11 Aug
  "Build experiment platform"          9 Aug to  1 Sep
  "Sweep the fabric"                   1 Sep to  7 Sep
  "Build FORGIVE"                      5 Sep to  9 Sep

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

BELOW THE AXIS: four solid ink diamonds on 2px ink stems, each with a
bold 20px label and a 16px sublabel:
  1 Sep  "run #117"  /  "seeds, go-back-N"
  6 Sep  "run #120"  /  "8 configurations"
   7 Sep  "run #121"  /  "FORGIVE"
  8 Sep  "run #122"  /  "budget sweep"

CLOSING LINE:
  "One paired comparison takes a day, and a full run takes several
  days. We built DCS runners, made 184 commits, ran four cluster jobs, and
  covered 180 configurations."

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
  "Thirteen seeds improved on the baseline"

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
  section label  "PAIRED SEEDS"
  "3.91 %" at 58px bold
  "faster 20-step run, 95 % CI [1.13, 6.68] %" at 16px
  a 1px paper-30 divider
  "153 ms" at 58px bold
  "reduction in the slowest all-reduce, CI [5, 302] ms" at 16px

CLOSING LINE:
  "On the four seeds whose slowest all-reduce exceeds 1.3 s, DBLP cuts that
  all-reduce by 434 to 716 ms; mild seeds barely change."

SPEAKER NOTE: "Seeds are eight-digit chunks of pi, fixed before the run.
The two runs share one random stream, so the messages the baseline drops
are exactly the ones the policy considers. Quote the slowest all-reduce
as 153 ms, never as a percentage."

===============================================================
SLIDE 5 of 8
===============================================================

Two scatter panels side by side, equal width, sharing one vertical axis
label.

HEADLINE, 34px bold, two sentences:
  "Prevented trims explain the saving; discarded bytes do not."

GLOSS LINE directly beneath the headline, 16px, ink at 55%:
  "A trim drops packet payload and forwards its header."

SHARED VERTICAL AXIS, labelled "20-step savings (ms)",
ticks at
-600, -300, 0, 300, 600 and 900, gridlines ink-12, a heavier ink-30 line
at zero.

LEFT PANEL, titled "Versus prevented trims". Marks in
ink-100 with a dashed ink-55 least-squares line. Horizontal axis "Packet
trims prevented (millions)", ticks at -40, -20, 0, 20, 40, 60 and 80.
Place "r = 0.93" at 58px bold inside the panel, upper left, with generous
space around it.

RIGHT PANEL, titled "Versus discarded gradient bytes". Marks in ink-55,
no fit line. Horizontal axis "Discarded gradient (GB)", ticks at
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
  "Each seed discards about 2 GB, which predicts nothing."
  "The slope is 11.9 ms per million trims prevented."
  "The policy regresses on the three seeds where it adds trims."

CLOSING LINE:
  "With go-back-N, discarding 1.98 GiB of gradient removes 156 GiB from the
  wire because one trimmed packet rewinds a whole window."

SPEAKER NOTE: "This is what makes the result an explanation rather than a
percentage, and it is what told us where the gain would not appear, which
is the next slide."

===============================================================
SLIDE 6 of 8
===============================================================

This slide states the scope of the result. It must not read as an
apology.

HEADLINE, 34px bold:
  "Go-back-N drives the gain; selective repeat removes it"

VISUAL: horizontal bar chart on a logarithmic axis from 1x to 1000x
across the left two thirds, titled "Go-back-N overhead versus selective
repeat, same workload and burst". One bar
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
  "Time to clear a seven-sender burst"               15x to  78x
      "go-back-N 423 to 1798 ms    selective repeat 23 to 29 ms"
  "All-reduce time, burst step"                      12x to  53x
      "go-back-N 205 to 935 ms    selective repeat 17.6 ms"
  "20-step run time"                                3.7x to 5.6x
      "go-back-N 4503 to 6795 ms    selective repeat 1210 ms"

READING LINE directly beneath the chart, 16px, ink at 55%:
  "At equal workload, go-back-N creates 110 to 520x more trimmed bytes."

RIGHT THIRD: an ink panel with paper text:
  section label  "NETWORK SWEEP"
  "8 configurations" at 34px bold
  "All 64 ranks used selective repeat, and we swept congestion control,
  fan-in, and spine oversubscription. We set the criteria before the run."
  a 1px paper-30 divider
  "We required switches to trim at least half a byte per byte sent. The
  most congested configuration reached 0.24."
  "We required the burst to take at least a fifth of training time. The
  most congested configuration reached 0.62 %."

CLOSING LINE, two sentences:
  "Relief across our go-back-N arms is 3.9 to 11.1 %, while the
  selective-repeat arm gains 0.78 %. All bounded-loss results in our
  review use go-back-N-like recovery."

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
  "FORGIVE applies DBLP under congestion control"

LEFT HALF: three stacked statements, 22px apart, each with its key figure
at 34px bold on its own line above 20px body text.

  "24 %"
  "With selective repeat, DCQCN adds this much to the 20-step run on the
  most congested configuration while reducing trimming eightfold. Rate
  reductions create the slowdown rather than repair."

  "10.4 to 10.9 %"
  "FORGIVE recovers that time by letting the receiver accept trimmed loss
  and allowing senders with budget remaining to ignore rate reductions
  until the receiver refuses. It uses 6.3 % of data-parallel bytes."

  "4 to 5x"
  "FORGIVE recovers 4 to 5x more time per discarded gradient percent than
  sender drop at every budget we tested."

RIGHT HALF: a scatter chart with two connected series, under a section
label reading "PRELIMINARY: THREE SEEDS, ONE FABRIC, ONE CONGESTION
CONTROLLER". Horizontal axis "Gradient bytes discarded (% of all
data-parallel bytes)", ticks at 0, 10, 20, 30, 40 and 50. Vertical axis "Training time
recovered (%)", ticks at 0, 3, 6, 9, 12, 15 and 18. Shade the band from
0.7 % to 3.3 % in ink-12, labelled at 14px "MLT (NSDI 2024) reports
models tolerating 0.7 % to 3.3 %". Draw a dashed ink-30 vertical line at
10 %, labelled "MLT's ceiling at a fixed quality target".

  Series A, ink-100, solid line with filled circles, labelled directly
  "FORGIVE", points as (x, y):
    (6.4, 10.6)   (8.5, 12.5)   (9.4, 13.3)   (9.2, 13.0)

  Series B, ink-55, solid line with hollow circles, labelled directly
  "Sender drop", points as (x, y):
    (7.7, 2.9)   (15.7, 5.3)   (31.5, 11.4)   (47.9, 16.2)

CLOSING LINE:
  "Above a budget of 0.2, the gain flattens, and discarded gradient levels
  off near 9.3 % because trimming stops before the budget is spent."

SPEAKER NOTE: "Present this as ongoing, not as a result. Read the chart
as: further right means more gradient thrown away, higher means more
training time back, so the better mechanism is the one that climbs
fastest while staying left. The design borrows from transports the field
already trusts: the receiver drives
repair the way selective acknowledgement does, the budget is a ledger
rather than a probability, and the exemption revokes itself on the
receiver's first refusal, so it cannot outlive what justified it.
Dropping at the sender only overtakes on time past a budget of about
0.45, where it is throwing away a third of every gradient, and no
published tolerance result reaches there."

===============================================================
SLIDE 8 of 8
===============================================================

HEADLINE, 34px bold:
  "We closed two July questions and scoped the other two"

VISUAL: a two-by-two grid of cards, 16px radius, 1px ink border, paper
fill, equal size, 22px gutter. Each card carries a monospace number at
28px in ink-30, a bold 20px question, and 20px body. Put a status chip in
each card's top right: 8px radius, ink-100 fill, paper text, 14px,
reading either "CLOSED" or "SCOPED".

  Card 01, chip "SCOPED", question "Sparsification":
    "We model pure drop without error feedback, separately from
    compression. Mixing the two creates a second uncontrolled lossy layer."

  Card 02, chip "CLOSED", question "Compute and transport interleaving":
    "Chakra traces show 5.4 ms of compute per node overlapping the run, so
    we report exposed communication time. The overlap prevents us from
    quoting the preprint headline."

  Card 03, chip "SCOPED", question "CLR identification":
    "The simulator has no gradients, so it cannot host a detector. The
    schedule is pinned from CLR detection literature."

  Card 04, chip "CLOSED", question "Centralized traffic versus ring traffic":
    "Fan-in multiplies switch trimming 2.7x, while spine oversubscription
    multiplies it 5.5x. Seven-to-one fan-in models hub-and-spoke pressure
    at one NIC and is the most congested configuration."

CLOSING LINE:
  "Two questions are closed by construction; the other two require
  hardware that a simulator cannot provide."

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

Context, in case a caption needs it. The numbers come from four cluster
runs of an ASTRA-sim and ns-3 simulation on a University of Toronto
cluster, between 1 and 8 September 2026. Each result is a pair of
simulated runs that share a seed and a random stream, so their times can
be subtracted. Trimming is a switch discarding a packet's payload and
forwarding its header, which is how this fabric signals congestion.
Go-back-N makes a sender re-send everything from the lost packet onward;
selective repeat re-sends only what was lost. The audience did not run
any of this, so prefer a plain description over the project's shorthand
in anything visible on a slide.
