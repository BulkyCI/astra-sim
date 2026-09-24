# Draws five metric figures from local release bundles: delivered share per (rank, step), fabric cost per
# configuration, tensor-parallel collective time against the p_low baseline, goodput against loss across the
# budget sweep, and the exemption duty cycle per step. Usage: SP=<bundle root with r123/ r125/ r126/ r127/> python forgive-metrics.py <output dir>
# Every summary counter used is cross-checked against the per-flow telemetry; the run prints the mismatch count.
import csv, json, os, sys, statistics as st
from collections import defaultdict
SP=os.environ['SP']; OUT=sys.argv[1]; PNG=os.environ.get('PNG')
SEEDS=(9550582,23172535,94081284); S_ALG=68_359_375; CRIT={1,2,3,20}; DP_TOTAL=191_406_250_000
def arm_dir(base,s):
    d=f'{base}-seed-{s}'
    return f'{d}/seed_{s}/recovery_policy' if os.path.isdir(f'{d}/seed_{s}') else d
W4=f'{SP}/r123/ex/ring-3d-regime-64-dcqcn-direct7-4to1-exempt'
ARMS={  # name -> function seed -> dir
 'DCQCN baseline': lambda s: f'{SP}/r126/ex/ring-3d-regime-64-dcqcn-direct7-4to1-zero-seed-{s}',
 'p_low baseline': lambda s: f'{W4}-p01-seed-{s}/seed_{s}/fixed_p_low_baseline',
 'forgiveness, CC on': lambda s: f'{SP}/r126/ex/ring-3d-regime-64-dcqcn-direct7-4to1-recovery-p01-seed-{s}',
 'FORGIVE': lambda s: f'{SP}/r127/ex/ring-3d-regime-64-dcqcn-direct7-4to1-exempt-p01-single-seed-{s}',
 'FORGIVE + pacing 0.25': lambda s: f'{SP}/r127/ex/ring-3d-regime-64-dcqcn-direct7-4to1-exempt-p01-b25-seed-{s}',
 'budget in full at step start': lambda s: f'{SP}/r127/ex/ring-3d-regime-64-dcqcn-direct7-4to1-exempt-p01-owed-seed-{s}',
 'exemption never withdrawn': lambda s: f'{SP}/r127/ex/ring-3d-regime-64-dcqcn-direct7-4to1-exempt-p01-noreengage-seed-{s}',
 'no congestion control': lambda s: f'{SP}/r126/ex/ring-3d-regime-64-none-direct7-4to1-zero-seed-{s}',
}
def summary(d):
    f=d+'/summary_certified.json'
    return json.load(open(f if os.path.exists(f) else d+'/summary.json'))
def flows(d):
    return csv.DictReader(open(d+'/telemetry/flow_events.csv'))
def coll(d):
    span={}; per={}; tp={}
    for r in csv.DictReader(open(d+'/telemetry/collective_events.csv')):
        s,e=int(r['start_time_ns']),int(r['end_time_ns']); stp=int(r['training_step'])
        if r['parallelism_domain']=='dp':
            k=(int(r['rank']),stp); per[k]=per.get(k,0)+(e-s); lo,hi=span.get(stp,(s,e)); span[stp]=(min(lo,s),max(hi,e))
        elif r['parallelism_domain']=='tp':
            k=(stp,r['workload_node_id']); lo,hi=tp.get(k,(s,e)); tp[k]=(min(lo,s),max(hi,e))
    return per,span,sum(hi-lo for lo,hi in tp.values())/1e6
def dp_stats(d):
    owed=defaultdict(int); forg=defaultdict(int); ex=defaultdict(float); ft=defaultdict(float); cnp=0; to=0; retx=0
    for r in flows(d):
        cnp+=int(r.get('cnp_received') or 0); to+=int(r.get('timeouts') or 0); retx+=int(r.get('retransmitted_bytes') or 0)
        if r['parallelism_domain']!='dp' or r['flow_kind']!='foreground_payload': continue
        k=(int(r['dst']),int(r['training_step'])); owed[k]+=int(r['logical_bytes']); forg[k]+=int(r.get('forgiven_bytes') or 0)
        stp=int(r['training_step']); s,e=int(r['start_time_ns']),int(r['end_time_ns']); ft[stp]+=e-s
        if r.get('cc_exempt')=='true':
            g=int(r.get('cc_exempt_granted_ns') or 0); ob=int(r.get('cc_obeying_ns') or 0)
            ex[stp]+=max(0,(e-g)-ob)
    return owed,forg,ex,ft,cnp,to,retx
res={}; checks=[]
for name,f in ARMS.items():
    R=res[name]={'shares_nc':[],'shares_c':[],'fabric':defaultdict(list),'tp_rel':[],'duty':defaultdict(list),'goodput':[],'loss':[]}
    for s in SEEDS:
        d=f(s); sm=summary(d); per,span,tpms=coll(d); owed,forg,ex,ft,cnp,to,retx=dp_stats(d)
        share={k:1-forg[k]/owed[k] for k in owed}
        R['shares_nc']+= [v for k,v in share.items() if k[1] not in CRIT]; R['shares_c']+=[v for k,v in share.items() if k[1] in CRIT]
        tr=sm['transport_recovery']
        R['fabric']['retransmitted bytes, % of bytes offered'].append(100*tr['retransmitted_bytes']/sm['total_physical_bytes'])
        R['fabric']['trim ratio W, %'].append(100*sm['network_health']['W'])
        R['fabric']['retransmission timeouts'].append(tr['timeout_count'])
        R['fabric']['CNPs received, millions'].append(tr['cnp_received_count']/1e6)
        checks.append((name,s,'timeouts summary vs flows',tr['timeout_count'],to)); checks.append((name,s,'cnp summary vs flows',tr['cnp_received_count'],cnp))
        checks.append((name,s,'forgiven summary vs flows',sm.get('forgiveness',{}).get('forgiven_bytes',0),sum(forg.values())))
        checks.append((name,s,'retx summary vs flows',tr['retransmitted_bytes'],retx))
        bt=coll(f'{W4}-p01-seed-{s}/seed_{s}/fixed_p_low_baseline')[2]; R['tp_rel'].append(100*(tpms/bt-1))
        for stp in ft: R['duty'][stp].append(100*ex[stp]/ft[stp] if ft[stp] else 0)
        g=[sum(S_ALG*share[(rk,stp)] for rk in range(64))/(hi-lo) for stp,(lo,hi) in span.items() if stp not in CRIT]
        R['goodput'].append(st.mean(g)); R['loss'].append(100*sum(forg.values())/DP_TOTAL)
    if name=='FORGIVE': checks.append((name,'all','min delivered share (cert 0.900 to 0.909)',min(R['shares_nc']),min(R['shares_c'])))
# budget sweep points: v1 (old rules) and vesting/pacing
SWEEP={'v1 0.05':(f'{SP}/r125/ex/ring-3d-regime-64-dcqcn-direct7-4to1-exempt-p005',None),'v1 0.1':(f'{W4}-p01',None),'v1 0.2':(f'{W4}-p02',None),'v1 0.4':(f'{W4}',None),'v1 0.6':(f'{W4}-p06',None),'v1 0.4, no schedule':(f'{W4}-allsteps',None),
       'pacing 0.05 at 0.1 (old rules)':(f'{SP}/r125/ex/ring-3d-regime-64-dcqcn-direct7-4to1-exempt-p01-b05',None),'pacing 0.1 at 0.1 (old rules)':(f'{SP}/r125/ex/ring-3d-regime-64-dcqcn-direct7-4to1-exempt-p01-b10',None)}
sweep={}
for name,(base,_) in SWEEP.items():
    pts=[]
    seeds=SEEDS if name!='v1 0.4' else (28410270,81117450,9550582,23172535,94081284)
    for s in seeds:
        d=arm_dir(base,s)
        if not os.path.isdir(d): continue
        per,span,_=coll(d); owed,forg,*_=dp_stats(d); share={k:1-forg[k]/owed[k] for k in owed}
        g=st.mean(sum(S_ALG*share[(rk,stp)] for rk in range(64))/(hi-lo) for stp,(lo,hi) in span.items() if stp not in CRIT)
        pts.append((100*sum(forg.values())/DP_TOTAL,g))
    sweep[name]=pts
for name in ('FORGIVE','FORGIVE + pacing 0.25'): sweep[name+' (vesting)']=list(zip(res[name]['loss'],res[name]['goodput']))
json.dump({'checks':checks,'sweep':sweep,'summary':{n:{'tp_rel':r['tp_rel'],'fabric':dict(r['fabric']),'goodput':r['goodput'],'loss':r['loss'],'min_share_nc':min(r['shares_nc']),'min_share_c':min(r['shares_c']),'median_share_nc':st.median(r['shares_nc']),'duty':{k:v for k,v in r['duty'].items()}} for n,r in res.items()}},open(f'{SP}/metrics2.json','w'),indent=1,default=float)
bad=[c for c in checks if c[2]!='min delivered share (cert 0.900 to 0.909)' and c[3]!=c[4]]
print('checks total',len(checks),'mismatches',len(bad)); [print(b) for b in bad[:10]]
print([c for c in checks if 'min delivered' in c[2]])
for n,r in res.items(): print(f"{n:30s} tp_rel {min(r['tp_rel']):+.1f}..{max(r['tp_rel']):+.1f}  retx {min(r['fabric']['retransmitted bytes, % of bytes offered']):.2f}..{max(r['fabric']['retransmitted bytes, % of bytes offered']):.2f}  W {min(r['fabric']['trim ratio W, %']):.2f}..{max(r['fabric']['trim ratio W, %']):.2f}  TO {min(r['fabric']['retransmission timeouts'])}..{max(r['fabric']['retransmission timeouts'])}  CNP {min(r['fabric']['CNPs received, millions']):.2f}..{max(r['fabric']['CNPs received, millions']):.2f} M  min share nc {min(r['shares_nc']):.3f} c {min(r['shares_c']):.4f}")
for n,p in sweep.items(): print(n, [(round(a,2),round(b,1)) for a,b in p])

import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'svg.fonttype':'none'})
cols={'DCQCN baseline':'#444444','p_low baseline':'#1f77b4','forgiveness, CC on':'#2ca02c','FORGIVE':'#d62728','FORGIVE + pacing 0.25':'#ff7f0e','budget in full at step start':'#8c564b','exemption never withdrawn':'#e377c2','no congestion control':'#9467bd'}
def save(fig,name):
    fig.tight_layout(); fig.savefig(f'{OUT}/{name}.svg')
    if PNG: fig.savefig(f'{PNG}/{name}.png',dpi=130)
    plt.close(fig)
# A: delivered share CDF
fig,ax=plt.subplots(figsize=(6.4,3.3))
for key,lab,c in (('shares_nc','non-critical steps, p = 0.1 (3 072 samples)','#d62728'),('shares_c','critical steps, p = 0.005 (768 samples)','#1f77b4')):
    v=sorted(res['FORGIVE'][key]); ax.plot(v,[(i+1)/len(v) for i in range(len(v))],color=c,lw=1.6,label=lab)
ax.axvline(0.9,color='#d62728',ls=':',lw=1); ax.axvline(0.995,color='#1f77b4',ls=':',lw=1)
ax.text(0.9005,0.5,'bound 1 - p = 0.900',rotation=90,fontsize=7,color='#d62728',va='center'); ax.text(0.9955,0.5,'bound 0.995',rotation=90,fontsize=7,color='#1f77b4',va='center')
ax.set_xlabel('share of owed gradient bytes delivered per (rank, step), FORGIVE at p = 0.1, 3 seeds'); ax.set_ylabel('CDF'); ax.set_xlim(0.89,1.0005); ax.set_ylim(0,1); ax.grid(alpha=0.3); ax.legend(fontsize=8,loc='upper left',frameon=False)
ax.set_title('Delivered share per rank and step against the loss bound, direct7 at 4:1',fontsize=9); save(fig,'dp-delivered-share-cdf')
# B: fabric cost, 4 panels
names=list(ARMS); fig,axs=plt.subplots(1,4,figsize=(11,3.4))
for ax,metric in zip(axs,['retransmitted bytes, % of bytes offered','trim ratio W, %','retransmission timeouts','CNPs received, millions']):
    m=[st.mean(res[n]['fabric'][metric]) for n in names]; lo=[m[i]-min(res[n]['fabric'][metric]) for i,n in enumerate(names)]; hi=[max(res[n]['fabric'][metric])-m[i] for i,n in enumerate(names)]
    ax.barh(range(len(names)),m,xerr=[lo,hi],color=[cols[n] for n in names],capsize=2,alpha=0.85); ax.invert_yaxis(); ax.set_yticks(range(len(names)))
    ax.set_yticklabels(names if ax is axs[0] else ['']*len(names),fontsize=8); ax.set_xlabel(metric,fontsize=8); ax.grid(axis='x',alpha=0.3)
    for i,v in enumerate(m): ax.text(v+hi[i]+0.02*max(m),i,f'{v:,.2f}' if max(m)<100 else f'{v:,.0f}',va='center',fontsize=7)
    ax.set_xlim(0,max(m)*1.35)
fig.suptitle('What each configuration costs the fabric, direct7 at 4:1, budget 0.1 where a budget applies (3 seeds: bar = mean, whisker = min to max)',fontsize=9); save(fig,'fabric-cost-per-configuration')
# C: TP collective time relative to p_low baseline
fig,ax=plt.subplots(figsize=(7.2,3.4)); nm=[n for n in names if n!='p_low baseline']
m=[st.mean(res[n]['tp_rel']) for n in nm]; lo=[m[i]-min(res[n]['tp_rel']) for i,n in enumerate(nm)]; hi=[max(res[n]['tp_rel'])-m[i] for i,n in enumerate(nm)]
ax.barh(range(len(nm)),m,xerr=[lo,hi],color=[cols[n] for n in nm],capsize=3,alpha=0.85); ax.invert_yaxis(); ax.set_yticks(range(len(nm))); ax.set_yticklabels(nm,fontsize=8); ax.axvline(0,color='k',lw=0.8)
ax.set_xlabel('tensor-parallel all-reduce time, % change against the p_low baseline on the same seed\n(per-collective span across its 8 ranks, summed over steps; 3 seeds, bar = mean, whisker = min to max)',fontsize=7)
ax.set_title('Collateral effect on tensor-parallel collectives sharing the leaf, direct7 at 4:1',fontsize=9); ax.grid(axis='x',alpha=0.3); save(fig,'tp-collective-time-vs-baseline')
# D: goodput vs loss sweep
OFF={'pacing 0.05 at 0.1 (old rules)':(-6,8),'pacing 0.1 at 0.1 (old rules)':(6,-12),'v1 0.1':(-38,-14),'FORGIVE (vesting)':(6,-12),'FORGIVE + pacing 0.25 (vesting)':(6,6),'v1 0.05':(6,-4)}
fig,ax=plt.subplots(figsize=(7.2,4.2))
for n,p in sweep.items():
    if not p: continue
    xs=[a for a,b in p]; ys=[b for a,b in p]; mx,my=st.mean(xs),st.mean(ys)
    mk='o' if n.startswith('v1') else ('s' if 'vesting' in n else '^'); c='#1f77b4' if n.startswith('v1') else ('#d62728' if 'vesting' in n else '#ff7f0e')
    ax.errorbar(mx,my,xerr=[[mx-min(xs)],[max(xs)-mx]],yerr=[[my-min(ys)],[max(ys)-my]],fmt=mk,color=c,ms=5,capsize=2,lw=1)
    ax.annotate(n,(mx,my),textcoords='offset points',xytext=OFF.get(n,(5,4)),fontsize=7)
base=st.mean(res['p_low baseline']['goodput']); ax.axhline(base,color='#1f77b4',ls=':',lw=1); ax.text(0.3,base+1.5,'p_low baseline',fontsize=7,color='#1f77b4')
ax.axhline(st.mean(res['no congestion control']['goodput']),color='#9467bd',ls='--',lw=1); ax.text(30,st.mean(res['no congestion control']['goodput'])+1.5,'no congestion control',fontsize=7,color='#9467bd')
ax.set_xlabel('gradient bytes forgiven, % of data-parallel bytes'); ax.set_ylabel('DP all-reduce goodput, GB/s (non-critical steps)')
ax.set_title('Goodput against loss across the budget sweep, direct7 at 4:1\n(circles: v1 rules, #123; squares: vesting, #127; triangles: pacing, old rules, #125; 3 seeds, 5 at budget 0.4)',fontsize=8)
ax.grid(alpha=0.3); save(fig,'goodput-vs-loss-sweep')
# E: exemption duty cycle per step
fig,ax=plt.subplots(figsize=(7.2,3.4))
for n in ('FORGIVE','FORGIVE + pacing 0.25','budget in full at step start','exemption never withdrawn'):
    steps=sorted(res[n]['duty']); me=[st.mean(res[n]['duty'][s]) for s in steps]; lo=[min(res[n]['duty'][s]) for s in steps]; hi=[max(res[n]['duty'][s]) for s in steps]
    ax.plot(steps,me,color=cols[n],lw=1.6,marker='o',ms=3,label=n); ax.fill_between(steps,lo,hi,color=cols[n],alpha=0.15,lw=0)
for c in CRIT: ax.axvspan(c-0.5,c+0.5,color='k',alpha=0.06,lw=0)
ax.set_xticks(range(1,21)); ax.set_ylim(0,100); ax.set_xlabel('training step (shaded: critical steps at p_low = 0.005)'); ax.set_ylabel('share of DP flow time spent exempt\nfrom congestion control, %')
ax.set_title('Exemption duty cycle per step: exempt flow time / total DP flow time, direct7 at 4:1, budget 0.1, 3 seeds',fontsize=9); ax.grid(alpha=0.3); ax.legend(fontsize=8,loc='lower center',frameon=False,ncol=2)
save(fig,'exemption-duty-cycle-per-step'); print('figures written')
