#!/usr/bin/env python3

'''
Visualize the output of derive_curves.py: for each retuned Delphes module
(ChargedHadronTrackingEfficiency, ElectronTrackingEfficiency,
MuonTrackingEfficiency, ChargedHadronMomentumSmearing), plot the offline
formula and the resulting HLT formula on the same axes, together with the
raw data-driven curve derive_curves.py measured (the ratio, for efficiency;
the extra sigma, for resolution) - so the effect of "offline formula" x/+
"data curve" -> "HLT formula" is directly visible, not just its end result.

The offline and HLT curves are read from the actual .tcl cards (not
recomputed from curves_qcd.json independently), so what's plotted is
exactly what generate_hlt_card.py produced - if you edit either card by
hand afterwards, or regenerate it with different --min-count/--max-sigma
thresholds, this plot reflects that.

One figure per module, one panel per |eta| bin (from curves_qcd.json's own
binning), saved to hlteff/plots/ by default.

Usage:
  python plot_curves.py [--curves PATH] [--offline-card PATH] [--hlt-card PATH]
                         [--outdir DIR]
'''

import os
import sys
import json
import argparse

import numpy as np
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from delphes_formula import evaluate_formula, extract_formula_block

HLTEFF_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(HLTEFF_DIR)

DEFAULT_CURVES = os.path.join(HLTEFF_DIR, 'curves_qcd.json')
DEFAULT_OFFLINE_CARD = os.path.join(REPO_DIR, 'delphes_cards', 'delphes_card_CMS_JetClassII_onlyFatJet.tcl')
DEFAULT_HLT_CARD = os.path.join(REPO_DIR, 'delphes_cards', 'delphes_card_CMS_JetClassII_onlyFatJet_HLT.tcl')
DEFAULT_OUTDIR = os.path.join(HLTEFF_DIR, 'plots')

EFFICIENCY_MODULES = {
    'chargedHadron': 'ChargedHadronTrackingEfficiency',
    'electron': 'ElectronTrackingEfficiency',
    'muon': 'MuonTrackingEfficiency',
}

plt.rcParams.update({
    'font.size': 13,
    'axes.labelsize': 14,
    'xtick.labelsize': 12,
    'ytick.labelsize': 12,
    'legend.fontsize': 11,
})


def fine_pt_grid(pt_edges, n_per_decade=60):
    lo, hi = pt_edges[0], pt_edges[-1]
    n = max(2, int(n_per_decade * (np.log10(hi) - np.log10(lo))))
    return np.logspace(np.log10(lo), np.log10(hi), n)


def sample_formula(formula_text, eta, pt_values):
    return np.array([evaluate_formula(formula_text, pt, eta) for pt in pt_values])


def step_edges(edges, values):
    ### (x, y) suitable for ax.step(x, y, where='post') representing a
    # piecewise-constant function equal to values[i] on [edges[i], edges[i+1])
    x = list(edges)
    y = list(values) + [values[-1]]
    return x, y


def plot_efficiency(curves, offline_text, hlt_text, cat, module, eta_edges, pt_edges, outdir):
    offline_formula = extract_formula_block(offline_text, module, 'EfficiencyFormula')
    hlt_formula = extract_formula_block(hlt_text, module, 'EfficiencyFormula')
    data = curves['categories'][cat]
    ne = len(eta_edges) - 1
    pt_fine = fine_pt_grid(pt_edges)

    fig, axes = plt.subplots(1, ne, figsize=(7 * ne, 5.5), sharey=True)
    if ne == 1:
        axes = [axes]

    for ie, ax in enumerate(axes):
        eta_c = 0.5 * (eta_edges[ie] + eta_edges[ie + 1])

        offline_y = sample_formula(offline_formula, eta_c, pt_fine)
        hlt_y = sample_formula(hlt_formula, eta_c, pt_fine)
        ax.plot(pt_fine, offline_y, color='dodgerblue', linewidth=2.5, label='offline card')
        ax.plot(pt_fine, hlt_y, color='darkorchid', linewidth=2.5, label='HLT card (generated)')

        ratio = [r if r is not None else np.nan for r in data['efficiency_ratio'][ie]]
        n_off = data['n_offline'][ie]
        rx, ry = step_edges(pt_edges, ratio)
        ax.step(rx, ry, where='post', color='gray', linewidth=1.5, linestyle=':',
                label='raw data ratio (HLT-matched / offline)')
        # mark bins with too few offline candidates to be trustworthy
        for ip in range(len(pt_edges) - 1):
            if n_off[ip] < 200:
                ax.axvspan(pt_edges[ip], pt_edges[ip + 1], color='gray', alpha=0.08, linewidth=0)

        ax.set_xscale('log')
        ax.set_ylim(0, 1.05)
        ax.set_xlabel(r'Particle $p_{T}$ [GeV]')
        ax.minorticks_on()
        ax.grid(True, which='major', linestyle='-', alpha=0.4)
        ax.grid(True, which='minor', linestyle=':', alpha=0.2)
        ax.set_title(r'${:g} < |\eta| \leq {:g}$'.format(eta_edges[ie], eta_edges[ie + 1]), fontsize=13)
        ax.legend(loc='best')

    axes[0].set_ylabel('Efficiency')
    fig.suptitle('{} tracking efficiency'.format(cat), fontsize=15)
    fig.tight_layout()

    outpath = os.path.join(outdir, 'efficiency_{}.png'.format(cat))
    fig.savefig(outpath, dpi=150)
    plt.close(fig)
    print('Saved', outpath)


def plot_resolution(curves, offline_text, hlt_text, eta_edges, pt_edges, outdir):
    offline_formula = extract_formula_block(offline_text, 'ChargedHadronMomentumSmearing', 'ResolutionFormula')
    hlt_formula = extract_formula_block(hlt_text, 'ChargedHadronMomentumSmearing', 'ResolutionFormula')
    data = curves['categories']['chargedHadron']
    ne = len(eta_edges) - 1
    pt_fine = fine_pt_grid(pt_edges)

    fig, axes = plt.subplots(1, ne, figsize=(7 * ne, 5.5), sharey=True)
    if ne == 1:
        axes = [axes]

    for ie, ax in enumerate(axes):
        eta_c = 0.5 * (eta_edges[ie] + eta_edges[ie + 1])

        offline_y = sample_formula(offline_formula, eta_c, pt_fine)
        hlt_y = sample_formula(hlt_formula, eta_c, pt_fine)
        ax.plot(pt_fine, offline_y, color='dodgerblue', linewidth=2.5, label='offline card')
        ax.plot(pt_fine, hlt_y, color='darkorchid', linewidth=2.5, label='HLT card (generated)')

        extra = [s if s is not None else np.nan for s in data['sigma_extra_pt'][ie]]
        n_pairs = data['n_matched_pairs'][ie]
        rx, ry = step_edges(pt_edges, extra)
        ax.step(rx, ry, where='post', color='gray', linewidth=1.5, linestyle=':',
                label='raw extra smearing (data)')
        for ip in range(len(pt_edges) - 1):
            if n_pairs[ip] < 200:
                ax.axvspan(pt_edges[ip], pt_edges[ip + 1], color='gray', alpha=0.08, linewidth=0)

        ax.set_xscale('log')
        ax.set_yscale('log')
        ax.set_xlabel(r'Particle $p_{T}$ [GeV]')
        ax.minorticks_on()
        ax.grid(True, which='major', linestyle='-', alpha=0.4)
        ax.grid(True, which='minor', linestyle=':', alpha=0.2)
        ax.set_title(r'${:g} < |\eta| \leq {:g}$'.format(eta_edges[ie], eta_edges[ie + 1]), fontsize=13)
        ax.legend(loc='best')

    axes[0].set_ylabel(r'Relative $p_{T}$ resolution $\sigma(p_{T})/p_{T}$')
    fig.suptitle('Charged hadron momentum resolution', fontsize=15)
    fig.tight_layout()

    outpath = os.path.join(outdir, 'resolution_chargedHadron.png')
    fig.savefig(outpath, dpi=150)
    plt.close(fig)
    print('Saved', outpath)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--curves', default=DEFAULT_CURVES)
    parser.add_argument('--offline-card', default=DEFAULT_OFFLINE_CARD)
    parser.add_argument('--hlt-card', default=DEFAULT_HLT_CARD)
    parser.add_argument('--outdir', default=DEFAULT_OUTDIR)
    args = parser.parse_args()

    with open(args.curves) as f:
        curves = json.load(f)
    eta_edges = curves['binning']['eta_edges']
    pt_edges = curves['binning']['pt_edges']

    with open(args.offline_card) as f:
        offline_text = f.read()
    with open(args.hlt_card) as f:
        hlt_text = f.read()

    os.makedirs(args.outdir, exist_ok=True)

    for cat, module in EFFICIENCY_MODULES.items():
        plot_efficiency(curves, offline_text, hlt_text, cat, module, eta_edges, pt_edges, args.outdir)

    plot_resolution(curves, offline_text, hlt_text, eta_edges, pt_edges, args.outdir)


if __name__ == '__main__':
    main()
