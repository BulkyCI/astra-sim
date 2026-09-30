# The incast figure of the paper plus one series, FORGIVE without the incast,
# drawn from the release bundles in the style of the paper's restyled incast
# figure (scripts/rebuild_incast_figure.py in the paper repository: Okabe-Ito
# colours, one line style and marker per series, bold coloured legend text,
# bold axis labels, hatched bars for runs without the incast).
#
# Usage: SP=<bundle root> python incast-with-forgive-no-incast.py <out.pdf>
# The root holds fig/ex/ (run #130 bundles, 1:1 no incast) and r131/ex/ (run
# #131, the incast wave). Numbers are recomputed from telemetry, not read
# from the earlier PDF; they agree with it to the millisecond.
import csv, json, os, sys, statistics as st

SP = os.environ['SP']; OUT = sys.argv[1]
SEEDS = (9550582, 23172535, 94081284)
F = f'{SP}/fig/ex/ring-3d-regime-64'; I = f'{SP}/r131/ex/ring-3d-regime-64'
# label, directory per seed, colour, line style, marker, incast?
SERIES = [
    ('Baseline (no incast)',  lambda s: f'{F}-dcqcn-direct7-1to1-exempt-p01-seed-{s}/seed_{s}/fixed_p_low_baseline', '#0072B2', '--', 'o', False),
    ('No CC (no incast)',     lambda s: f'{I}-none-direct7-1to1-zero-seed-{s}',                                        '#882255', ':',  's', False),
    ('FORGIVE (no incast)',   lambda s: f'{F}-dcqcn-direct7-1to1-exempt-p01-seed-{s}/seed_{s}/recovery_policy',        '#CC79A7', ':',  'P', False),
    ('No CC (incast)',        lambda s: f'{I}-none-direct7-1to1-zero-burst63-seed-{s}',                                '#D55E00', '-',  '^', True),
    ('DCQCN, no loss (incast)', lambda s: f'{I}-dcqcn-direct7-1to1-zero-burst63-seed-{s}',                             '#A07800', '-.', 'D', True),
    ('FORGIVE (incast)',      lambda s: f'{I}-dcqcn-direct7-1to1-exempt-p01-burst63-seed-{s}/seed_{s}/recovery_policy', '#009E73', '-',  'v', True),
]
BASELINE_INCAST = lambda s: f'{I}-dcqcn-direct7-1to1-exempt-p01-burst63-seed-{s}/seed_{s}/fixed_p_low_baseline'

def spans(d):
    span = {}
    for r in csv.DictReader(open(d + '/telemetry/collective_events.csv')):
        if r['parallelism_domain'] != 'dp': continue
        k = int(r['training_step']); a, b = int(r['start_time_ns']), int(r['end_time_ns'])
        lo, hi = span.get(k, (a, b)); span[k] = (min(lo, a), max(hi, b))
    return {k: (hi - lo) / 1e6 for k, (lo, hi) in span.items()}
jct = lambda d: json.load(open(d + '/summary.json'))['completion_time_ns_max'] / 1e6

data = {}
for label, f, *_ in SERIES:
    runs = [(spans(f(s)), jct(f(s))) for s in SEEDS]
    data[label] = runs
    print(f'{label:26s} JCT mean {st.mean(j for _, j in runs):.1f} ms (range {min(j for _, j in runs):.1f} to {max(j for _, j in runs):.1f})')
base_incast = [jct(BASELINE_INCAST(s)) for s in SEEDS]
print(f'{"Baseline (incast)":26s} JCT mean {st.mean(base_incast):.1f} ms (range {min(base_incast):.1f} to {max(base_incast):.1f})')

import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.patches import Patch
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 7, 'axes.labelsize': 8, 'axes.labelweight': 'bold', 'pdf.fonttype': 42})
fig = plt.figure(figsize=(3.45, 4.25))
top = fig.add_axes((.18, .575, .78, .24))
steps = list(range(1, 21)); lines = []
for label, _, color, style, marker, _ in SERIES:
    runs = data[label]
    mean = [st.mean(r[0][k] for r, _ in [(x, 0) for x in runs]) for k in steps]
    lo = [min(x[0][k] for x in runs) for k in steps]; hi = [max(x[0][k] for x in runs) for k in steps]
    top.fill_between(steps, lo, hi, color=color, alpha=.14, linewidth=0)
    line, = top.plot(steps, mean, color=color, label=label, linestyle=style, marker=marker, markersize=2.5, markeredgewidth=.4, linewidth=1.05)
    lines.append(line)
top.set(yscale='log', xlim=(0.5, 20.5), xlabel='Training step', ylabel='Data-parallel AllReduce\ntime per step (ms)')
top.set_xticks([1, 5, 10, 15, 20]); top.axvspan(9.5, 10.5, color='black', alpha=.07, linewidth=0); top.grid(alpha=.2, linewidth=.4)
legend = fig.legend(handles=lines, loc='upper center', bbox_to_anchor=(.5, .995), ncol=2, fontsize=6.4, frameon=False,
                    handlelength=2.3, columnspacing=.8, labelspacing=.65, borderaxespad=0)
for text, line in zip(legend.get_texts(), lines):
    text.set_color(line.get_color()); text.set_fontweight('bold')

# bars: the three runs without the incast, then the four with it
rows = [('Baseline', 'Baseline (no incast)', '#0072B2', False), ('No CC', 'No CC (no incast)', '#882255', False), ('FORGIVE', 'FORGIVE (no incast)', '#CC79A7', False),
        ('Baseline', None, '#0072B2', True), ('No CC', 'No CC (incast)', '#D55E00', True), ('DCQCN (no loss)', 'DCQCN, no loss (incast)', '#A07800', True), ('FORGIVE', 'FORGIVE (incast)', '#009E73', True)]
bottom = fig.add_axes((.34, .09, .62, .30))
for row, (short, key, color, incast) in enumerate(rows):
    vals = base_incast if key is None else [j for _, j in data[key]]
    mean = st.mean(vals)
    bottom.barh(row, mean, height=.68, color=color, edgecolor='white', hatch=None if incast else '////', linewidth=.5)
    bottom.errorbar(mean, row, xerr=[[mean - min(vals)], [max(vals) - mean]], fmt='none', ecolor='black', elinewidth=.7, capsize=2)
    bottom.text(max(vals) + 35, row, str(round(mean)), va='center', fontsize=7)
bottom.set_yticks(range(len(rows)), labels=[r[0] for r in rows])
for label in bottom.get_yticklabels(): label.set_fontweight('bold')
bottom.set(ylim=(len(rows) - .4, -.6), xlim=(0, 2050), xlabel='Job completion time (ms)')
bottom.set_xticks([0, 500, 1000, 1500, 2000]); bottom.grid(axis='x', alpha=.2, linewidth=.4); bottom.set_axisbelow(True)
fig.legend(handles=[Patch(facecolor='.6', edgecolor='white', hatch='////', label='No incast'), Patch(facecolor='.6', label='Incast at step 10')],
           loc='center', bbox_to_anchor=(.57, .45), ncol=2, frameon=False, prop={'size': 7, 'weight': 'bold'}, handlelength=1.5, columnspacing=1)
for ax in (top, bottom):
    ax.tick_params(length=2.5, width=.6, pad=2)
    for spine in ax.spines.values(): spine.set_linewidth(.6)
fig.savefig(OUT); fig.savefig(OUT[:-4] + '.png', dpi=300); print('wrote', OUT)
