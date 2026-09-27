# Draws the paper's FORGIVE figures as PDF (no goodput figures: delivered bytes fall with forgiveness, so goodput confounds the comparison) at IEEE column widths from local
# release bundles, design of record only (main 59cf16c rules): direct7 at 4:1,
# budget 0.1 where a budget applies, seeds 9550582, 23172535, 94081284.
#
# Usage: SP=<bundle root> python paper-figures.py <output dir>
# The root holds fig/ex/<asset name>/ (runs #123 baseline inside
# seed_<s>/fixed_p_low_baseline, #126 zero and none, #127 single, b25, owed)
# and r132/ex/<asset name>/ (P = 0, forgive-only "recovery", the budget sweep).
#
# Every figure recomputes from telemetry/collective_events.csv and
# telemetry/flow_events.csv; the fabric counters come from summary.json and
# are cross-checked against the per-flow rows (the run prints the mismatches).
import csv, json, os, sys, statistics as st
from collections import defaultdict

SP = os.environ['SP']; OUT = sys.argv[1]
SEEDS = (9550582, 23172535, 94081284); S_ALG = 68_359_375; CRIT = {1, 2, 3, 20}; DP_TOTAL = 191_406_250_000
F = f'{SP}/fig/ex/ring-3d-regime-64'; R = f'{SP}/r132/ex/ring-3d-regime-64'
BASE = lambda s: f'{F}-dcqcn-direct7-4to1-exempt-p01-seed-{s}/seed_{s}/fixed_p_low_baseline'
ARMS = {  # Table IV order
    'Baseline ($p=0.005$ dropping)': BASE,
    'DCQCN, no loss':                lambda s: f'{F}-dcqcn-direct7-4to1-zero-seed-{s}',
    'Forgiveness only':              lambda s: f'{R}-dcqcn-direct7-4to1-recovery-p01-single-seed-{s}',
    'FORGIVE without vesting':       lambda s: f'{F}-dcqcn-direct7-4to1-exempt-p01-owed-seed-{s}',
    'FORGIVE, $P=0$':                lambda s: f'{R}-dcqcn-direct7-4to1-exempt-p01-p0-single-seed-{s}',
    'FORGIVE, $P=0.25$':             lambda s: f'{F}-dcqcn-direct7-4to1-exempt-p01-b25-seed-{s}',
    'FORGIVE':                       lambda s: f'{F}-dcqcn-direct7-4to1-exempt-p01-single-seed-{s}',
    'No congestion control':         lambda s: f'{F}-none-direct7-4to1-zero-seed-{s}',
}
SWEEP = {  # label -> dir function; the vested budget sweep of run #132 plus the #127 points
    '0.05': lambda s: f'{R}-dcqcn-direct7-4to1-exempt-p005-single-seed-{s}',
    '0.1':  ARMS['FORGIVE'],
    '0.2':  lambda s: f'{R}-dcqcn-direct7-4to1-exempt-p02-single-seed-{s}',
    '0.4':  lambda s: f'{R}-dcqcn-direct7-4to1-exempt-single-seed-{s}',
    '0.6':  lambda s: f'{R}-dcqcn-direct7-4to1-exempt-p06-single-seed-{s}',
    '0.4, schedule off': lambda s: f'{R}-dcqcn-direct7-4to1-exempt-allsteps-single-seed-{s}',
}
COL = {'Baseline ($p=0.005$ dropping)': '#d62728', 'DCQCN, no loss': '#7f7f7f', 'Forgiveness only': '#17becf',
       'FORGIVE without vesting': '#8c564b', 'FORGIVE, $P=0$': '#2ca02c', 'FORGIVE, $P=0.25$': '#ff7f0e',
       'FORGIVE': '#1f77b4', 'No congestion control': '#222222'}
LS = {'No congestion control': '--'}

def summary(d):
    f = d + '/summary_certified.json'
    return json.load(open(f if os.path.exists(f) else d + '/summary.json'))

def coll(d):
    per = {}; span = {}; tp = {}
    for r in csv.DictReader(open(d + '/telemetry/collective_events.csv')):
        s, e = int(r['start_time_ns']), int(r['end_time_ns']); stp = int(r['training_step'])
        if r['parallelism_domain'] == 'dp':
            k = (int(r['rank']), stp); per[k] = per.get(k, 0) + (e - s)
            lo, hi = span.get(stp, (s, e)); span[stp] = (min(lo, s), max(hi, e))
        elif r['parallelism_domain'] == 'tp':
            k = (stp, r['workload_node_id']); lo, hi = tp.get(k, (s, e)); tp[k] = (min(lo, s), max(hi, e))
    return per, span, sum(hi - lo for lo, hi in tp.values()) / 1e6

def dp_stats(d):
    owed = defaultdict(int); forg = defaultdict(int); ex = defaultdict(float); ft = defaultdict(float); cnp = to = retx = 0
    for r in csv.DictReader(open(d + '/telemetry/flow_events.csv')):
        cnp += int(r.get('cnp_received') or 0); to += int(r.get('timeouts') or 0); retx += int(r.get('retransmitted_bytes') or 0)
        if r['parallelism_domain'] != 'dp' or r['flow_kind'] != 'foreground_payload': continue
        k = (int(r['dst']), int(r['training_step'])); owed[k] += int(r['logical_bytes']); forg[k] += int(r.get('forgiven_bytes') or 0)
        stp = int(r['training_step']); s, e = int(r['start_time_ns']), int(r['end_time_ns']); ft[stp] += e - s
        if r.get('cc_exempt') == 'true':
            g = int(r.get('cc_exempt_granted_ns') or 0); ob = int(r.get('cc_obeying_ns') or 0); ex[stp] += max(0, (e - g) - ob)
    return owed, forg, ex, ft, cnp, to, retx

def measure(d):
    sm = summary(d); per, span, tpms = coll(d); owed, forg, ex, ft, cnp, to, retx = dp_stats(d)
    share = {k: 1 - forg[k] / owed[k] for k in owed}
    g = {stp: sum(S_ALG * share[(rk, stp)] for rk in range(64)) / (hi - lo) for stp, (lo, hi) in span.items()}
    tr = sm['transport_recovery']
    fab = {'retransmitted bytes (%)': 100 * tr['retransmitted_bytes'] / sm['total_physical_bytes'],
           'bytes trimmed (%)': 100 * sm['network_health']['W'],
           'retransmission timeouts': tr['timeout_count'],
           'congestion notification packets (millions)': tr['cnp_received_count'] / 1e6}
    checks = [('timeouts', tr['timeout_count'], to), ('cnp', tr['cnp_received_count'], cnp), ('retx', tr['retransmitted_bytes'], retx),
              ('forgiven', sm.get('forgiveness', {}).get('forgiven_bytes', 0), sum(forg.values()))]
    return dict(per=per, share=share, goodput=g, tpms=tpms, fab=fab, duty={s_: 100 * ex[s_] / ft[s_] for s_ in ft if ft[s_]},
                loss=100 * sum(forg.values()) / DP_TOTAL, checks=checks)

res = {}; bad = []
for name, f in ARMS.items():
    res[name] = [measure(f(s)) for s in SEEDS]
    for s, m in zip(SEEDS, res[name]):
        bad += [(name, s) + c for c in m['checks'] if c[1] != c[2]]
base_tp = {s: coll(BASE(s))[2] for s in SEEDS}
print('summary-vs-telemetry mismatches:', len(bad)); [print(b) for b in bad[:8]]
nc_goodput = lambda m: st.mean(v for k, v in m['goodput'].items() if k not in CRIT)
for name in ARMS:
    gs = [nc_goodput(m) for m in res[name]]; ls_ = [m['loss'] for m in res[name]]
    print(f"{name:32s} goodput {min(gs):.1f} to {max(gs):.1f} GB/s  loss {min(ls_):.2f} to {max(ls_):.2f} %  "
          f"retx {min(m['fab']['retransmitted bytes (%)'] for m in res[name]):.2f} to {max(m['fab']['retransmitted bytes (%)'] for m in res[name]):.2f} %  "
          f"min share nc {min(v for m in res[name] for k, v in m['share'].items() if k[1] not in CRIT):.3f}")
sweep = {lab: [measure(f(s)) for s in SEEDS] for lab, f in SWEEP.items()}
for lab, ms in sweep.items():
    print(f"sweep {lab:18s} loss {min(m['loss'] for m in ms):.2f} to {max(m['loss'] for m in ms):.2f} %  goodput {min(nc_goodput(m) for m in ms):.1f} to {max(nc_goodput(m) for m in ms):.1f} GB/s")

import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
# House style of the paper's existing figures: sans-serif, bold axis labels, framed legend, light grid,
# the proposed mechanism in blue and the baseline in red.
plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 7, 'axes.labelsize': 7, 'axes.labelweight': 'bold', 'legend.fontsize': 6,
                     'legend.frameon': True, 'legend.framealpha': 0.9, 'legend.edgecolor': '#cccccc', 'legend.fancybox': False,
                     'xtick.labelsize': 6, 'ytick.labelsize': 6, 'pdf.fonttype': 42, 'axes.grid': True, 'grid.alpha': 0.3, 'grid.linewidth': 0.4})
def save(fig, name):
    fig.savefig(f'{OUT}/{name}.pdf'); plt.close(fig); print('wrote', name)
def band(ax, name, key):
    steps = list(range(1, 21)); v = [[m[key][s_] for m in res[name]] for s_ in steps]
    ax.plot(steps, [st.mean(x) for x in v], LS.get(name, '-'), color=COL[name], lw=1.1, label=name)
    ax.fill_between(steps, [min(x) for x in v], [max(x) for x in v], color=COL[name], alpha=0.2, lw=0)
def steps_axis(ax):
    for c in CRIT: ax.axvspan(c - 0.5, c + 0.5, color='k', alpha=0.07, lw=0)
    ax.set_xlim(0.5, 20.5); ax.set_xticks([1, 5, 10, 15, 20]); ax.set_xlabel('training step')
LINES = ['Baseline ($p=0.005$ dropping)', 'Forgiveness only', 'FORGIVE, $P=0$', 'FORGIVE', 'No congestion control']

# 3. CDF of per-(rank, step) DP all-reduce time, non-critical steps
fig, ax = plt.subplots(figsize=(3.45, 1.9))
for n in LINES:
    t = sorted(v / 1e6 for m_ in res[n] for k, v in m_['per'].items() if k[1] not in CRIT)
    ax.plot(t, [(i + 1) / len(t) for i in range(len(t))], LS.get(n, '-'), color=COL[n], lw=1.1, label=n)
ax.set_ylim(0, 1); ax.set_xlabel('data-parallel AllReduce time per rank and step (ms)'); ax.set_ylabel('CDF')
ax.legend(loc='lower right', handlelength=1.6); fig.tight_layout(pad=0.3); save(fig, 'dp-allreduce-time-cdf')

# 4. delivered share against the bound, FORGIVE
fig, ax = plt.subplots(figsize=(3.45, 1.7))
for crit, lab, c, bnd in ((False, 'non-critical steps, $p=0.1$', '#1f77b4', 0.9), (True, 'critical steps, $p=0.005$', '#ff7f0e', 0.995)):
    v = sorted(x for m_ in res['FORGIVE'] for k, x in m_['share'].items() if (k[1] in CRIT) == crit)
    ax.plot(v, [(i + 1) / len(v) for i in range(len(v))], color=c, lw=1.1, label=lab); ax.axvline(bnd, color=c, ls=':', lw=0.8)
ax.set_xlim(0.89, 1.0005); ax.set_ylim(0, 1); ax.set_xlabel('share of expected bytes delivered per rank and step'); ax.set_ylabel('CDF')
ax.legend(loc='upper left', handlelength=1.6); fig.tight_layout(pad=0.3); save(fig, 'dp-delivered-share-cdf')

# 5. fabric cost, four panels, full width
names = list(ARMS)
fig, axs = plt.subplots(1, 4, figsize=(7.1, 2.05), sharey=True)
for ax, metric in zip(axs, ['retransmitted bytes (%)', 'bytes trimmed (%)', 'retransmission timeouts', 'congestion notification packets (millions)']):
    xl = {'retransmission timeouts': 'retransmission\ntimeouts', 'congestion notification packets (millions)': 'congestion notification\npackets (millions)'}.get(metric, metric)
    vals = [[x['fab'][metric] for x in res[n]] for n in names]; mm = [st.mean(v) for v in vals]
    ax.barh(range(len(names)), mm, xerr=[[mm[i] - min(v) for i, v in enumerate(vals)], [max(v) - mm[i] for i, v in enumerate(vals)]],
            color=[COL[n] for n in names], capsize=2, alpha=0.9, height=0.7)
    ax.set_xlabel(xl); ax.grid(axis='y', visible=False); ax.set_xlim(0, max(mm) * 1.38)
    for i, v in enumerate(mm): ax.text(v + (max(vals[i]) - v) + 0.02 * max(mm), i, f'{v:,.1f}' if max(mm) < 100 else f'{v:,.0f}', va='center', fontsize=5.5)
axs[0].set_yticks(range(len(names))); axs[0].set_yticklabels(names); axs[0].invert_yaxis()
fig.tight_layout(pad=0.3, w_pad=0.6); save(fig, 'fabric-cost-per-configuration')

# 6. tensor-parallel collective time against the baseline, same seed
nm = names[1:]; rel = [[100 * (x['tpms'] / base_tp[s] - 1) for s, x in zip(SEEDS, res[n])] for n in nm]; mm = [st.mean(v) for v in rel]
fig, ax = plt.subplots(figsize=(3.45, 1.7))
ax.barh(range(len(nm)), mm, xerr=[[mm[i] - min(v) for i, v in enumerate(rel)], [max(v) - mm[i] for i, v in enumerate(rel)]],
        color=[COL[n] for n in nm], capsize=2, alpha=0.9, height=0.7)
ax.set_yticks(range(len(nm))); ax.set_yticklabels(nm); ax.invert_yaxis(); ax.axvline(0, color='k', lw=0.6); ax.grid(axis='y', visible=False)
ax.set_xlabel('tensor-parallel AllReduce time vs. baseline (%)'); fig.tight_layout(pad=0.3); save(fig, 'tp-collective-time-vs-baseline')

# 8. exemption duty cycle per step
fig, ax = plt.subplots(figsize=(3.45, 1.95))
for n in ('FORGIVE', 'FORGIVE, $P=0.25$', 'FORGIVE, $P=0$', 'FORGIVE without vesting'): band(ax, n, 'duty')
steps_axis(ax); ax.set_ylim(0, 100); ax.set_ylabel('flow time under exemption (%)')
ax.legend(loc='lower center', ncol=2, handlelength=1.6, bbox_to_anchor=(0.5, 1.0), borderaxespad=0.1)
fig.tight_layout(pad=0.3); save(fig, 'exemption-duty-cycle-per-step')

# 9. budget sweep: completion-time reduction and loss against the vested budget
jct = lambda d: summary(d)['completion_time_ns_max'] / 1e6
base_jct = {s_: jct(BASE(s_)) for s_ in SEEDS}
def red(f): return [100 * (1 - jct(f(s_)) / base_jct[s_]) for s_ in SEEDS]
budgets = [5, 10, 20, 40, 60]; labs = ['0.05', '0.1', '0.2', '0.4', '0.6']  # budget on the axes in percent, so loss and budget share a unit
rd = [red(SWEEP[l]) for l in labs]; ls_ = [[m_['loss'] for m_ in sweep[l]] for l in labs]
off_rd = red(SWEEP['0.4, schedule off']); off_ls = [m_['loss'] for m_ in sweep['0.4, schedule off']]
print('sweep reduction', [(l, round(min(v), 1), round(max(v), 1)) for l, v in zip(labs, rd)], 'schedule off', round(min(off_rd), 1), round(max(off_rd), 1))
fig, (a, b) = plt.subplots(1, 2, figsize=(3.45, 1.75))
a.errorbar(budgets, [st.mean(v) for v in rd], yerr=[[st.mean(v) - min(v) for v in rd], [max(v) - st.mean(v) for v in rd]], fmt='s-', color='#1f77b4', ms=3.5, lw=1, capsize=1.5, label='FORGIVE')
a.errorbar([40], [st.mean(off_rd)], yerr=[[st.mean(off_rd) - min(off_rd)], [max(off_rd) - st.mean(off_rd)]], fmt='D', color='#9467bd', ms=3.5, capsize=1.5, label='$p=0.4$ on every step')
a.set_ylabel('completion-time\nreduction (%)'); a.set_ylim(0, 25)
b.errorbar(budgets, [st.mean(v) for v in ls_], yerr=[[st.mean(v) - min(v) for v in ls_], [max(v) - st.mean(v) for v in ls_]], fmt='s-', color='#1f77b4', ms=3.5, lw=1, capsize=1.5)
b.errorbar([40], [st.mean(off_ls)], yerr=[[st.mean(off_ls) - min(off_ls)], [max(off_ls) - st.mean(off_ls)]], fmt='D', color='#9467bd', ms=3.5, capsize=1.5)
b.plot([0, 45], [0, 45], ':', color='k', lw=0.8); b.text(24, 27.5, 'loss = budget', fontsize=6, rotation=45, ha='center', va='bottom')
b.set_ylabel('data-parallel\nbytes lost (%)'); b.set_ylim(0, 45)
for ax in (a, b): ax.set_xlim(0, 65); ax.set_xticks([0, 10, 20, 30, 40, 50, 60]); ax.set_xlabel('loss budget $p$ (%)')
a.legend(loc='lower right', handlelength=1.4); fig.tight_layout(pad=0.3, w_pad=0.8); save(fig, 'budget-sweep')

# 10. the 63-source incast on the 1:1 fabric (run #131 against the #130 no-burst baseline)
I = f'{SP}/r131/ex/ring-3d-regime-64'
INCAST = {
    'Baseline, no incast':               lambda s_: f'{F}-dcqcn-direct7-1to1-exempt-p01-seed-{s_}/seed_{s_}/fixed_p_low_baseline',
    'No congestion control, no incast':  lambda s_: f'{I}-none-direct7-1to1-zero-seed-{s_}',
    'No congestion control':            lambda s_: f'{I}-none-direct7-1to1-zero-burst63-seed-{s_}',
    'DCQCN, no loss':                   lambda s_: f'{I}-dcqcn-direct7-1to1-zero-burst63-seed-{s_}',
    'Baseline ($p=0.005$ dropping)':    lambda s_: f'{I}-dcqcn-direct7-1to1-exempt-p01-burst63-seed-{s_}/seed_{s_}/fixed_p_low_baseline',
    'Phase-aware dropping (DBLP)':      lambda s_: f'{I}-dcqcn-direct7-1to1-exempt-p01-burst63-seed-{s_}/seed_{s_}/dblp_policy',
    'FORGIVE':                          lambda s_: f'{I}-dcqcn-direct7-1to1-exempt-p01-burst63-seed-{s_}/seed_{s_}/recovery_policy',
}
ICOL = {'Baseline, no incast': '#d62728', 'No congestion control, no incast': '#222222', 'No congestion control': '#222222', 'DCQCN, no loss': '#7f7f7f',
        'Baseline ($p=0.005$ dropping)': '#d62728', 'Phase-aware dropping (DBLP)': '#9467bd', 'FORGIVE': '#1f77b4'}
ILS = {'No congestion control, no incast': ':', 'Baseline, no incast': ':'}
inc = {}
for n, f in INCAST.items():
    rows = []
    for s_ in SEEDS:
        d = f(s_); _, span, _ = coll(d); rows.append(({k: (hi - lo) / 1e6 for k, (lo, hi) in span.items()}, jct(d)))
    inc[n] = rows
    print(f"incast {n:32s} JCT {min(r[1] for r in rows):.1f} to {max(r[1] for r in rows):.1f} ms; step 10 span {min(r[0][10] for r in rows):.1f} to {max(r[0][10] for r in rows):.1f} ms")
fig, (a, b) = plt.subplots(2, 1, figsize=(3.45, 3.5), gridspec_kw={'height_ratios': [1.1, 1]})
steps = list(range(1, 21))
for n in ('Baseline, no incast', 'No congestion control, no incast', 'No congestion control', 'DCQCN, no loss', 'FORGIVE'):
    v = [[r[0][s_] for r in inc[n]] for s_ in steps]
    a.plot(steps, [st.mean(x) for x in v], ILS.get(n, '-'), color=ICOL[n], lw=1.0, label=n + (' (incast)' if n in ('No congestion control', 'DCQCN, no loss', 'FORGIVE') else ''))
    a.fill_between(steps, [min(x) for x in v], [max(x) for x in v], color=ICOL[n], alpha=0.2, lw=0)
a.set_yscale('log'); a.axvspan(9.5, 10.5, color='k', alpha=0.07, lw=0); a.set_xlim(0.5, 20.5); a.set_xticks([1, 5, 10, 15, 20])
a.set_xlabel('training step'); a.set_ylabel('data-parallel AllReduce\ntime per step (ms)')
h_, l_ = a.get_legend_handles_labels(); fig.legend(h_, l_, loc='upper center', handlelength=1.5, ncol=2, columnspacing=1.0, bbox_to_anchor=(0.5, 1.0))
nm = list(INCAST); mm = [st.mean(r[1] for r in inc[n]) for n in nm]
b.barh(range(len(nm)), mm, xerr=[[mm[i] - min(r[1] for r in inc[n]) for i, n in enumerate(nm)], [max(r[1] for r in inc[n]) - mm[i] for i, n in enumerate(nm)]],
       color=[ICOL[n] for n in nm], capsize=1.5, alpha=0.9, height=0.7, hatch=['//' if 'no incast' in n else '' for n in nm], edgecolor='white', lw=0.3)
b.set_yticks(range(len(nm))); b.set_yticklabels([n.replace(' ($p=0.005$ dropping)', '') for n in nm]); b.invert_yaxis(); b.grid(axis='y', visible=False)
for i, v in enumerate(mm): b.text(v + 25, i, f'{v:.0f}', va='center', fontsize=5.5)
b.set_xlim(0, max(mm) * 1.95); b.set_xlabel('job completion time (ms)')
from matplotlib.patches import Patch
b.legend(handles=[Patch(facecolor='#bbbbbb', edgecolor='white', hatch='//', label='no incast'), Patch(facecolor='#bbbbbb', label='63-source incast\nat step 10')], loc='lower right', handlelength=1.4)
fig.tight_layout(pad=0.3, h_pad=0.6, rect=(0, 0, 1, 0.87)); save(fig, 'incast-63-sources')
