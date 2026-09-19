#!/usr/bin/env python3

'''
Plot the impact-parameter dependence of the offline-to-HLT tracking
efficiency ratio measured by derive_ip_curves.py:

  - ip_efficiency_<category>.png: HLT/offline ratio vs offline |d0| (the
    variable Delphes efficiency formulas can use), one panel per |eta| bin,
    one line per (coarse) track-pT group;
  - ip_dz_acceptance.png: the same for prompt charged hadrons vs offline
    |dz| (HLT tracking's z acceptance around the leading vertex, which a
    Delphes formula cannot express - see derive_ip_curves.py).

The ratio is n_matched / n_offline; reading it as an HLT efficiency *relative
to offline* assumes the offline efficiency is uniform in the impact
parameter (see derive_ip_curves.py). Error bars are binomial.

Usage:
  python plot_ip_curves.py [--curves PATH] [--outdir DIR]
'''

import os
import json
import argparse

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HLTEFF_DIR = os.path.dirname(os.path.abspath(__file__))

# coarse track-pT groups (GeV) the fine pT bins are summed into for plotting
PT_GROUPS = [(0.5, 1.2), (1.2, 3.0), (3.0, 10.0), (10.0, 40.0), (40.0, None)]
# ordered groups -> one sequential hue, light -> dark (blue steps 250..650)
GROUP_COLORS = ['#86b6ef', '#5598e7', '#2a78d6', '#1c5cab', '#104281']
INK, INK_MUTED, GRID = '#0b0b0b', '#52514e', '#e4e3df'
MIN_COUNT = 30


def group_counts(n_off, n_match, pt_edges, lo, hi):
    '''Sum the (eta, pt, x) count grids over the fine pT bins inside [lo, hi).'''
    sel = [i for i in range(len(pt_edges) - 1)
           if pt_edges[i] >= lo - 1e-9 and (hi is None or pt_edges[i + 1] <= hi + 1e-9)]
    return n_off[:, sel, :].sum(axis=1), n_match[:, sel, :].sum(axis=1)


def x_positions(edges):
    '''Log-scale-friendly bin representatives: geometric centre, first/last bins handled.'''
    xs = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        if lo <= 0:
            xs.append(hi / 2.0)
        elif hi > 1e8:
            xs.append(lo * 2.0)
        else:
            xs.append(np.sqrt(lo * hi))
    return np.array(xs)


def style_axis(ax):
    ax.set_xscale('log')
    ax.set_ylim(0, 1.05)
    ax.grid(True, which='major', color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for s in ('top', 'right'):
        ax.spines[s].set_visible(False)
    for s in ('left', 'bottom'):
        ax.spines[s].set_color(INK_MUTED)
    ax.tick_params(colors=INK_MUTED, labelcolor=INK)


def plot_panels(n_off, n_match, pt_edges, eta_edges, x_edges, xlabel, title, outpath, edge_labels):
    ne = len(eta_edges) - 1
    fig, axes = plt.subplots(1, ne, figsize=(6.2 * ne, 4.6), sharey=True)
    axes = np.atleast_1d(axes)
    xs = x_positions(x_edges)
    for ie, ax in enumerate(axes):
        for (lo, hi), color in zip(PT_GROUPS, GROUP_COLORS):
            off, mat = group_counts(n_off, n_match, pt_edges, lo, hi)
            n, m = off[ie].astype(float), mat[ie].astype(float)
            ok = n >= MIN_COUNT
            if not ok.any():
                continue
            r = np.where(ok, m / np.maximum(n, 1), np.nan)
            err = np.where(ok, np.sqrt(np.clip(r * (1 - r), 0, None) / np.maximum(n, 1)), np.nan)
            label = 'pT > {:g} GeV'.format(lo) if hi is None else 'pT {:g}-{:g} GeV'.format(lo, hi)
            ax.errorbar(xs[ok], r[ok], yerr=err[ok], color=color, linewidth=2, marker='o', markersize=6,
                        markeredgecolor='white', markeredgewidth=1, capsize=0, label=label)
        style_axis(ax)
        ax.set_xticks(xs)
        ax.set_xticklabels(edge_labels, rotation=0, fontsize=8)
        ax.minorticks_off()
        ax.set_xlabel(xlabel, color=INK)
        ax.set_title('|eta| {:g}-{:g}'.format(eta_edges[ie], eta_edges[ie + 1]), color=INK, fontsize=11)
    axes[0].set_ylabel('HLT / offline (matched fraction)', color=INK)
    axes[-1].legend(frameon=False, fontsize=9, labelcolor=INK, loc='upper right')
    fig.suptitle(title, color=INK, fontsize=12)
    fig.tight_layout()
    fig.savefig(outpath, dpi=150)
    plt.close(fig)
    print('wrote', outpath)


def edge_labels(edges):
    out = []
    for lo, hi in zip(edges[:-1], edges[1:]):
        out.append('>{:g}'.format(lo) if hi > 1e8 else '{:g}-{:g}'.format(lo, hi))
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--curves', default=os.path.join(HLTEFF_DIR, 'curves_ip_qcd.json'))
    parser.add_argument('--outdir', default=os.path.join(HLTEFF_DIR, 'plots', 'ip'))
    args = parser.parse_args()
    os.makedirs(args.outdir, exist_ok=True)

    with open(args.curves) as f:
        c = json.load(f)
    b = c['binning']
    pt_edges, eta_edges = b['pt_edges'], b['eta_edges']
    d0_edges, dz_edges = b['d0_edges_mm'], b['dz_edges_mm']
    src = c['source']
    note = '{} QCD jets, FullSim offline vs scouting'.format(src['n_jets_processed'])

    for cat, data in c['categories'].items():
        plot_panels(np.array(data['n_offline']), np.array(data['n_matched']), pt_edges, eta_edges, d0_edges,
                    'offline |d0| (mm)',
                    'HLT tracking relative to offline vs transverse impact parameter: {} ({})'.format(cat, note),
                    os.path.join(args.outdir, 'ip_efficiency_{}.png'.format(cat)), edge_labels(d0_edges))

    dza = c['dz_acceptance']
    plot_panels(np.array(dza['n_offline']), np.array(dza['n_matched']), pt_edges, eta_edges, dz_edges,
                'offline |dz| w.r.t. PV (mm)',
                'HLT tracking relative to offline vs |dz|: prompt charged hadrons, |dxy| < 0.1 mm ({})'.format(note),
                os.path.join(args.outdir, 'ip_dz_acceptance.png'), edge_labels(dz_edges))


if __name__ == '__main__':
    main()
