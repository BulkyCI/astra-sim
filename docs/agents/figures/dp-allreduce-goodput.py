# Draws the three data-parallel all-reduce goodput and completion-time figures
# from local release bundles. Usage: SP=<bundle root with r123/ r126/ r127/> python dp-allreduce-goodput.py <output dir>
# The bundle root holds the extracted release bundles of runs #123, #126 and #127 under r123/ex, r126/ex, r127/ex.
import csv, json, os, sys, statistics as st
from collections import defaultdict
SP=os.environ['SP']; OUT=sys.argv[1]
SEEDS=(9550582,23172535,94081284); S_ALG=68_359_375; CRIT={1,2,3,20}
ARMS={
 'DCQCN baseline (no loss)':        lambda s: f'{SP}/r126/ex/ring-3d-regime-64-dcqcn-direct7-4to1-zero-seed-{s}',
 'p_low baseline (0.5 % shed)':      lambda s: f'{SP}/r123/ex/ring-3d-regime-64-dcqcn-direct7-4to1-exempt-p01-seed-{s}/seed_{s}/fixed_p_low_baseline',
 'forgiveness, CC on, p = 0.1':      lambda s: f'{SP}/r126/ex/ring-3d-regime-64-dcqcn-direct7-4to1-recovery-p01-seed-{s}',
 'FORGIVE (vesting + CC exemption), p = 0.1': lambda s: f'{SP}/r127/ex/ring-3d-regime-64-dcqcn-direct7-4to1-exempt-p01-single-seed-{s}',
 'no congestion control':            lambda s: f'{SP}/r126/ex/ring-3d-regime-64-none-direct7-4to1-zero-seed-{s}',
}
def read(d):
    span={}; per={}  # per (rank,step) time ns
    for r in csv.DictReader(open(d+'/telemetry/collective_events.csv')):
        if r['parallelism_domain']!='dp': continue
        k=(int(r['rank']),int(r['training_step'])); s,e=int(r['start_time_ns']),int(r['end_time_ns'])
        per[k]=per.get(k,0)+(e-s)
        st_=int(r['training_step']); lo,hi=span.get(st_,(s,e)); span[st_]=(min(lo,s),max(hi,e))
    owed=defaultdict(int); forg=defaultdict(int)
    for r in csv.DictReader(open(d+'/telemetry/flow_events.csv')):
        if r['parallelism_domain']!='dp' or r['flow_kind']!='foreground_payload': continue
        k=(int(r['dst']),int(r['training_step'])); owed[k]+=int(r['logical_bytes']); forg[k]+=int(r.get('forgiven_bytes') or 0)
    share={k:1-forg[k]/owed[k] if owed[k] else 1.0 for k in per}
    return per,span,share
res={}
for name,f in ARMS.items():
    res[name]={'per_step_goodput':{}, 'rank_times_ms':[], 'summary':{}}
    step_g=defaultdict(list); times=[]; mean_nc=[]
    for s in SEEDS:
        per,span,share=read(f(s))
        g={}
        for stp,(lo,hi) in span.items():
            deliv=sum(S_ALG*share[(rk,stp)] for rk in range(64) if (rk,stp) in per)
            g[stp]=deliv/(hi-lo)  # bytes per ns = GB/s
            step_g[stp].append(g[stp])
        times += [per[(rk,stp)]/1e6 for (rk,stp) in per if stp not in CRIT]
        mean_nc.append(st.mean(g[stp] for stp in g if stp not in CRIT))
    res[name]['per_step_goodput']={stp:(min(v),st.mean(v),max(v)) for stp,v in step_g.items()}
    res[name]['rank_times_ms']=times
    res[name]['summary']={'goodput_nc_GBps_min':min(mean_nc),'goodput_nc_GBps_mean':st.mean(mean_nc),'goodput_nc_GBps_max':max(mean_nc),
        'allreduce_ms_median':st.median(times),'allreduce_ms_p99':sorted(times)[int(0.99*len(times))-1],'allreduce_ms_max':max(times)}
    print(f"{name:45s} goodput non-critical {min(mean_nc):.2f} to {max(mean_nc):.2f} GB/s; all-reduce median {st.median(times):.1f} ms p99 {sorted(times)[int(0.99*len(times))-1]:.1f} ms max {max(times):.1f}")
json.dump({k:{'per_step_goodput':v['per_step_goodput'],'summary':v['summary']} for k,v in res.items()},open(f'{SP}/goodput.json','w'),indent=1)

import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'svg.fonttype':'none'})
cols={'DCQCN baseline (no loss)':'#444444','p_low baseline (0.5 % shed)':'#1f77b4','forgiveness, CC on, p = 0.1':'#2ca02c','FORGIVE (vesting + CC exemption), p = 0.1':'#d62728','no congestion control':'#9467bd'}
ls={'no congestion control':'--'}
# Figure 1: per-step goodput
fig,ax=plt.subplots(figsize=(7.2,3.6))
for name,v in res.items():
    steps=sorted(v['per_step_goodput']); lo=[v['per_step_goodput'][s][0] for s in steps]; me=[v['per_step_goodput'][s][1] for s in steps]; hi=[v['per_step_goodput'][s][2] for s in steps]
    ax.plot(steps,me,ls.get(name,'-'),color=cols[name],label=name,lw=1.6,marker='o',ms=3); ax.fill_between(steps,lo,hi,color=cols[name],alpha=0.15,lw=0)
for c in CRIT: ax.axvspan(c-0.5,c+0.5,color='#000000',alpha=0.06,lw=0)
ax.set_xlabel('training step (shaded: critical steps 1, 2, 3, 20 at p_low = 0.005)'); ax.set_ylabel('DP all-reduce goodput, GB/s\n(delivered gradient bytes / step span, 64 ranks)')
ax.set_xticks(range(1,21)); ax.set_ylim(bottom=0); ax.grid(alpha=0.3); ax.legend(fontsize=8,loc='lower right',frameon=False)
ax.set_title('Data-parallel all-reduce goodput per step, direct7, 4:1, 3 seeds (line: mean, band: min to max)',fontsize=9)
fig.tight_layout(); fig.savefig(f'{OUT}/dp-allreduce-goodput-per-step.svg'); plt.close(fig)
# Figure 2: summary bars
fig,ax=plt.subplots(figsize=(7.6,3.4))
names=list(res); m=[res[n]['summary']['goodput_nc_GBps_mean'] for n in names]; lo=[m[i]-res[n]['summary']['goodput_nc_GBps_min'] for i,n in enumerate(names)]; hi=[res[n]['summary']['goodput_nc_GBps_max']-m[i] for i,n in enumerate(names)]
base=m[names.index('p_low baseline (0.5 % shed)')]
ax.barh(range(len(names)),m,xerr=[lo,hi],color=[cols[n] for n in names],alpha=0.85,capsize=3)
ax.set_yticks(range(len(names))); ax.set_yticklabels(names,fontsize=8); ax.invert_yaxis()
for i,v in enumerate(m): ax.text(v+hi[i]+3,i,f'{v:.0f} GB/s ({100*(v/base-1):+.0f} %)',va='center',fontsize=8)
ax.set_xlim(0,max(m)*1.32)
ax.set_xlabel('mean DP all-reduce goodput over the 16 non-critical steps, GB/s\n(3 seeds: bar = mean, whisker = min to max; % relative to the p_low baseline)',fontsize=8)
ax.set_title('Goodput = delivered gradient bytes / all-reduce span, 64 ranks, direct7 at 4:1',fontsize=9); ax.grid(axis='x',alpha=0.3)
fig.tight_layout(); fig.savefig(f'{OUT}/dp-allreduce-goodput-summary.svg'); plt.close(fig)
# Figure 3: CDF of per-(rank, step) all-reduce completion time
fig,ax=plt.subplots(figsize=(6.4,3.4))
for name,v in res.items():
    t=sorted(v['rank_times_ms']); y=[(i+1)/len(t) for i in range(len(t))]
    ax.plot(t,y,ls.get(name,'-'),color=cols[name],label=name,lw=1.6)
ax.set_xlabel('DP all-reduce completion time per (rank, step), ms\n(non-critical steps, 3 seeds, 3 072 samples per configuration)'); ax.set_ylabel('CDF')
ax.set_ylim(0,1); ax.grid(alpha=0.3); ax.legend(fontsize=8,loc='lower right',frameon=False)
ax.set_title('All-reduce completion time distribution, direct7, 4:1',fontsize=9)
fig.tight_layout(); fig.savefig(f'{OUT}/dp-allreduce-time-cdf.svg'); plt.close(fig)
print('figures written')
