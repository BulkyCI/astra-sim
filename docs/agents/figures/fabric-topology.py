# Draws the fabric topology figure (1:1, 2:1 and 4:1 configurations) with the direct<w> definition.
# Facts from experiments/ring_3d/topology.py (one 400 Gbps link per host-leaf and per leaf-live-spine pair, 5 us and 12.5 us one-way)
# and astra-sim/system/astraccl/native_collectives/collective_algorithm/AllToAll.cc (parallel_reduce = min(window, peers)).
# Usage: python fabric-topology.py <output dir>
import sys, os
import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch
OUT=sys.argv[1]; PNG=os.environ.get('PNG')
plt.rcParams.update({'font.family':'DejaVu Sans','font.size':8,'svg.fonttype':'none'})
LEAVES=8; HOSTS=8
def panel(ax,title,spines_designed,spines_failed,note):
    live=spines_designed-spines_failed
    ax.set_xlim(-0.5,LEAVES*10-0.5); ax.set_ylim(-3.2,13); ax.axis('off')
    ax.text(LEAVES*5-0.5,12.6,title,ha='center',va='top',fontsize=9,fontweight='bold')
    # spines
    sx=[LEAVES*10*(i+0.5)/spines_designed-0.5 for i in range(spines_designed)]
    for i,x in enumerate(sx):
        failed=i>=live
        ax.add_patch(Rectangle((x-3,9.2),6,1.4,fc='#dddddd' if failed else '#4c72b0',ec='#333333',lw=0.8,ls='--' if failed else '-'))
        ax.text(x,9.9,'spine' if not failed else 'spine (failed)',ha='center',va='center',fontsize=6.5,color='#333333' if failed else 'white')
    # leaves and hosts
    for l in range(LEAVES):
        lx=l*10+4
        ax.add_patch(Rectangle((lx-3.6,5.2),7.2,1.3,fc='#55a868',ec='#333333',lw=0.8)); ax.text(lx,5.85,f'leaf {l}',ha='center',va='center',fontsize=6.5,color='white')
        for i,x in enumerate(sx):
            if i<live: ax.plot([lx,x],[6.5,9.2],color='#888888',lw=0.5,zorder=0)
        for h in range(HOSTS):
            hx=lx-3.5+h*1.0; rank=l*8+h
            tp=(l==0); dp=(h==0)
            fc='#c44e52' if dp else ('#dd8452' if tp else '#f0f0f0')
            ax.add_patch(Rectangle((hx-0.4,1.6),0.8,1.6,fc=fc,ec='#333333',lw=0.5)); ax.plot([hx,hx],[3.2,5.2],color='#888888',lw=0.5,zorder=0)
        ax.text(lx,0.9,f'ranks {l*8} to {l*8+7}',ha='center',va='top',fontsize=6)
    ax.text(LEAVES*5-0.5,-1.4,note,ha='center',va='top',fontsize=7.5)
fig,axs=plt.subplots(3,1,figsize=(10.5,11.5))
panel(axs[0],'1:1, the non-oversubscribed configuration: 8 spines, none failed (profiles *_1to1_*)',8,0,'each leaf: 8 hosts x 400 Gbps in, 8 uplinks x 400 Gbps out')
panel(axs[1],'2:1, the designed fabric: 4 spines, none failed (profiles *_2to1_*)',4,0,'each leaf: 8 x 400 Gbps in, 4 x 400 Gbps out')
panel(axs[2],'4:1, the most congested configuration: 4 spines designed, 2 failed (profiles *_4to1_*)',4,2,'each leaf: 8 x 400 Gbps in, 2 live uplinks x 400 Gbps out; a failed spine is absent from the built fabric')
fig.text(0.5,0.035,
 'Two-tier leaf-spine Clos, 64 ranks: one host per rank, 8 hosts per leaf, every leaf linked to every live spine by one 400 Gbps link; host-to-leaf one-way delay 5 us, leaf-to-spine 12.5 us; '
 'per-flow ECMP across spines, no spraying; PFC off; packet trimming (forward trimmed data) with the trimmed class at 25 % WDRR weight.\n'
 'Tensor-parallel group = the 8 hosts of one leaf (orange, leaf 0: ranks 0 to 7); data-parallel group = the same host position on every leaf (red: ranks 0, 8, 16, ..., 56), so every DP flow crosses a spine. '
 'Oversubscription is the leaf ratio 8 x 400 in : live spines x 400 out.\n'
 'direct<w> (ASTRA-sim\'s AllToAll collective used for the DP all-reduce): each rank sends its shard to each of its 7 peers, keeping min(w, 7) transfers in flight at once to distinct peers in ring order; '
 'by symmetry it receives from as many at once. direct7 = all 7 peers at once (fan-out 7 and fan-in 7); direct2 = 2 at a time. The number bounds each direction, not their sum. ring = fan-in 1.',
 ha='center',va='bottom',fontsize=7.3,wrap=True)
fig.tight_layout(rect=(0,0.10,1,1)); fig.savefig(f'{OUT}/fabric-topology.svg')
if PNG: fig.savefig(f'{PNG}/fabric-topology.png',dpi=110)
print('ok')
