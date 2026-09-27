# Draws the two-panel FORGIVE figure for the DBLP paper: (a) elapsed training
# time at the end of each step and (b) utilization of the spine-facing links
# of a leaf during the data-parallel all-reduce, per step, on the most
# congested configuration (direct7, 4:1, two live spines), three seeds.
#
# Usage: SP=<bundle root> python forgive-time-utilization.py <out.pdf> [<out.svg>]
# The root holds the extracted bundles under fig/ex/<asset name>/ for runs #123
# (p_low baseline inside seed_<s>/fixed_p_low_baseline), #127 (FORGIVE
# p01_single) and #126 (no congestion control), and r132/ex/ for P = 0.
#
# Utilization is delivered bytes: for each leaf and step, the bytes of every
# data-parallel flow into the leaf's eight hosts from another leaf that
# started inside the leaf's data-parallel all-reduce span for that step,
# divided by 2 links x 400 Gbps x the span. Physical bytes (retransmissions
# included) are printed alongside for the record.
import csv, os, sys, statistics as st
from collections import defaultdict

SP = os.environ['SP']; OUT = sys.argv[1]; SVG = sys.argv[2] if len(sys.argv) > 2 else None
SEEDS = (9550582, 23172535, 94081284); CRIT = {1, 2, 3, 20}
LINKS = 2; RATE = 400e9  # spine-facing links per leaf at 4:1 and their rate, bit/s
ARMS = {
    'Baseline ($p=0.005$ dropping)': lambda s: f'{SP}/fig/ex/ring-3d-regime-64-dcqcn-direct7-4to1-exempt-p01-seed-{s}/seed_{s}/fixed_p_low_baseline',
    'FORGIVE, $P=0$':                       lambda s: f'{SP}/r132/ex/ring-3d-regime-64-dcqcn-direct7-4to1-exempt-p01-p0-single-seed-{s}',
    'FORGIVE':                              lambda s: f'{SP}/fig/ex/ring-3d-regime-64-dcqcn-direct7-4to1-exempt-p01-single-seed-{s}',
    'No congestion control':                lambda s: f'{SP}/fig/ex/ring-3d-regime-64-none-direct7-4to1-zero-seed-{s}',
}
leaf = lambda h: h // 8

def read(d):
    end = defaultdict(int)                 # step -> latest end over all collectives (ns)
    span = {}                              # (leaf, step) -> (lo, hi) of the DP all-reduce
    for r in csv.DictReader(open(d + '/telemetry/collective_events.csv')):
        stp = int(r['training_step']); s, e = int(r['start_time_ns']), int(r['end_time_ns'])
        end[stp] = max(end[stp], e)
        if r['parallelism_domain'] != 'dp': continue
        k = (leaf(int(r['rank'])), stp); lo, hi = span.get(k, (s, e)); span[k] = (min(lo, s), max(hi, e))
    deliv = defaultdict(int); phys = defaultdict(int)
    for r in csv.DictReader(open(d + '/telemetry/flow_events.csv')):
        if r['parallelism_domain'] != 'dp': continue
        src, dst = int(r['src']), int(r['dst'])
        if leaf(src) == leaf(dst): continue
        k = (leaf(dst), int(r['training_step']))
        if k not in span: continue
        lo, hi = span[k]; t0 = int(r['start_time_ns'])
        if not (lo <= t0 <= hi): continue
        deliv[k] += int(r['delivered_bytes'] or 0); phys[k] += int(r['physical_bytes'] or 0)
    util_d = {}; util_p = {}
    for k, (lo, hi) in span.items():
        cap = LINKS * RATE * (hi - lo) / 1e9 / 8  # bytes the links could carry in the span
        util_d[k] = deliv[k] / cap; util_p[k] = phys[k] / cap
    return end, util_d, util_p

res = {}
for name, f in ARMS.items():
    t_end = defaultdict(list); u_d = defaultdict(list); u_p = defaultdict(list)
    for s in SEEDS:
        end, ud, up = read(f(s))
        for stp, e in end.items(): t_end[stp].append(e / 1e6)
        by = defaultdict(list); byp = defaultdict(list)
        for (L, stp), v in ud.items(): by[stp].append(v); byp[stp].append(up[(L, stp)])
        for stp in by: u_d[stp].append(st.mean(by[stp])); u_p[stp].append(st.mean(byp[stp]))
    res[name] = (t_end, u_d, u_p)
    nc = [stp for stp in u_d if stp not in CRIT]
    print(f'{name:40s} end of step 20 {min(t_end[20]):.1f} to {max(t_end[20]):.1f} ms; '
          f'delivered-byte utilization, non-critical steps, mean {st.mean(st.mean(u_d[s_]) for s_ in nc):.3f} '
          f'(step range {min(st.mean(u_d[s_]) for s_ in nc):.3f} to {max(st.mean(u_d[s_]) for s_ in nc):.3f})')

import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 7, 'axes.labelsize': 7, 'axes.labelweight': 'bold', 'legend.fontsize': 6, 'legend.frameon': True, 'legend.framealpha': 0.9, 'legend.edgecolor': '#cccccc', 'legend.fancybox': False, 'xtick.labelsize': 6, 'ytick.labelsize': 6, 'pdf.fonttype': 42})
cols = {'Baseline ($p=0.005$ dropping)': '#d62728', 'FORGIVE, $P=0$': '#2ca02c', 'FORGIVE': '#1f77b4', 'No congestion control': '#222222'}
lss = {'No congestion control': '--'}
fig, (a, b) = plt.subplots(1, 2, figsize=(3.45, 1.55))
steps = list(range(1, 21))
for name, (t_end, u_d, _) in res.items():
    me = [st.mean(t_end[s]) for s in steps]; lo = [min(t_end[s]) for s in steps]; hi = [max(t_end[s]) for s in steps]
    a.plot(steps, me, lss.get(name, '-'), color=cols[name], lw=1.1, label=name); a.fill_between(steps, lo, hi, color=cols[name], alpha=0.2, lw=0)
    me = [100 * st.mean(u_d[s]) for s in steps]; lo = [100 * min(u_d[s]) for s in steps]; hi = [100 * max(u_d[s]) for s in steps]
    b.plot(steps, me, lss.get(name, '-'), color=cols[name], lw=1.1); b.fill_between(steps, lo, hi, color=cols[name], alpha=0.2, lw=0)
for ax in (a, b):
    for c in CRIT: ax.axvspan(c - 0.5, c + 0.5, color='k', alpha=0.07, lw=0)
    ax.set_xlim(0.5, 20.5); ax.set_xticks([1, 5, 10, 15, 20]); ax.set_xlabel('training step'); ax.grid(alpha=0.3, lw=0.4)
a.set_ylabel('elapsed time (ms)'); a.set_ylim(bottom=0); a.set_title('(a) completion time', fontsize=7)
b.set_ylabel('utilization (%)'); b.set_ylim(0, 100); b.set_title('(b) spine-link utilization', fontsize=7)
h, l = a.get_legend_handles_labels()
fig.legend(h, l, loc='lower center', ncol=2, handlelength=1.6, columnspacing=1.2, bbox_to_anchor=(0.5, -0.01))
fig.tight_layout(pad=0.3, w_pad=0.8, rect=(0, 0.17, 1, 1))
fig.savefig(OUT)
if SVG: fig.savefig(SVG)
print('wrote', OUT)
