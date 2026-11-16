#!/usr/bin/env python3

'''Visualize the output of derive_curves.py.

For each retuned Delphes module, plot the offline formula, the resulting HLT formula
and the raw data-driven curve on the same axes - the ratio for a multiplicative module,
the extra sigma for a quadrature one - so the step from offline formula and data curve
to HLT formula is visible rather than only its end result.

The offline and HLT curves are read from the actual .tcl cards rather than recomputed,
so the plot shows exactly what generate_hlt_card.py produced, including any later edit
or a regeneration with different options.

One figure per module, one panel per |eta| bin, saved to hlteff/plots/ by default.

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
RESOLUTION_MODULES = {
    'chargedHadron': 'ChargedHadronMomentumSmearing',
    'electron': 'ElectronMomentumSmearing',
    'muon': 'MuonMomentumSmearing',
}

plt.rcParams.update({
    'font.size': 13,
    'axes.labelsize': 14,
    'xtick.labelsize': 12,
    'ytick.labelsize': 12,
    'legend.fontsize': 11,
})


def fine_pt_grid(pt_edges, n_per_decade=60):
    '''A log-spaced pT grid spanning the bin edges, for drawing a smooth formula curve.
    '''
    lo, hi = pt_edges[0], pt_edges[-1]
    n = max(2, int(n_per_decade * (np.log10(hi) - np.log10(lo))))
    return np.logspace(np.log10(lo), np.log10(hi), n)


def sample_formula(formula_text, eta, pt_values):
    '''Evaluate a Delphes formula at one |eta| across a grid of pT values.'''
    return np.array([evaluate_formula(formula_text, pt=pt, eta=eta) for pt in pt_values])


def step_edges(edges, values):
    '''(x, y) for ax.step(..., where='post'), representing a piecewise-constant function
    equal to values[i] on [edges[i], edges[i+1]).
    '''
    x = list(edges)
    y = list(values) + [values[-1]]
    return x, y


def new_panel_figure(ne):
    '''A figure with one shared-y panel per |eta| bin.'''
    fig, axes = plt.subplots(1, ne, figsize=(7 * ne, 5.5), sharey=True)
    if ne == 1:
        axes = [axes]
    return fig, axes


def finish_panel(ax, eta_edges, ie, xlabel, logx=True, logy=False):
    '''Apply the shared axis styling, labels and |eta| title to one panel.'''
    if logx:
        ax.set_xscale('log')
    if logy:
        ax.set_yscale('log')
    ax.set_xlabel(xlabel)
    ax.minorticks_on()
    ax.grid(True, which='major', linestyle='-', alpha=0.4)
    ax.grid(True, which='minor', linestyle=':', alpha=0.2)
    ax.set_title(r'${:g} < |\eta| \leq {:g}$'.format(eta_edges[ie], eta_edges[ie + 1]), fontsize=13)
    ax.legend(loc='best')


def save(fig, outdir, name):
    '''Write the figure to outdir and close it.'''
    outpath = os.path.join(outdir, name)
    fig.tight_layout()
    fig.savefig(outpath, dpi=150)
    plt.close(fig)
    print('Saved', outpath)


def plot_efficiency(curves, offline_text, hlt_text, cat, module, eta_edges, pt_edges, outdir, min_count=200):
    '''Plot one tracking-efficiency module: offline and HLT formulas against the measured
    HLT/offline ratio.
    '''
    offline_formula = extract_formula_block(offline_text, module, 'EfficiencyFormula')
    hlt_formula = extract_formula_block(hlt_text, module, 'EfficiencyFormula')
    data = curves['categories'][cat]
    ne = len(eta_edges) - 1
    pt_fine = fine_pt_grid(pt_edges)

    fig, axes = new_panel_figure(ne)
    for ie, ax in enumerate(axes):
        eta_c = 0.5 * (eta_edges[ie] + eta_edges[ie + 1])
        ax.plot(pt_fine, sample_formula(offline_formula, eta_c, pt_fine), color='dodgerblue', linewidth=2.5, label='offline card')
        ax.plot(pt_fine, sample_formula(hlt_formula, eta_c, pt_fine), color='darkorchid', linewidth=2.5, label='HLT card (generated)')

        ratio = [r if r is not None else np.nan for r in data['efficiency_ratio'][ie]]
        n_off = data['n_offline'][ie]
        rx, ry = step_edges(pt_edges, ratio)
        ax.step(rx, ry, where='post', color='gray', linewidth=1.5, linestyle=':',
                label='raw data ratio (HLT-matched / offline)')
        for ip in range(len(pt_edges) - 1):
            if n_off[ip] < min_count:
                ax.axvspan(pt_edges[ip], pt_edges[ip + 1], color='gray', alpha=0.08, linewidth=0)

        ax.set_ylim(0, 1.05)
        finish_panel(ax, eta_edges, ie, r'Particle $p_{T}$ [GeV]')

    axes[0].set_ylabel('Efficiency')
    fig.suptitle('{} tracking efficiency'.format(cat), fontsize=15)
    save(fig, outdir, 'efficiency_{}.png'.format(cat))


def plot_pt_resolution(curves, offline_text, hlt_text, cat, module, eta_edges, pt_edges, outdir, min_pairs=200):
    '''Plot one momentum-resolution module: offline and HLT formulas against the measured
    extra sigma.
    '''
    offline_formula = extract_formula_block(offline_text, module, 'ResolutionFormula')
    hlt_formula = extract_formula_block(hlt_text, module, 'ResolutionFormula')
    data = curves['categories'][cat]
    ne = len(eta_edges) - 1
    pt_fine = fine_pt_grid(pt_edges)

    fig, axes = new_panel_figure(ne)
    for ie, ax in enumerate(axes):
        eta_c = 0.5 * (eta_edges[ie] + eta_edges[ie + 1])
        ax.plot(pt_fine, sample_formula(offline_formula, eta_c, pt_fine), color='dodgerblue', linewidth=2.5, label='offline card')
        ax.plot(pt_fine, sample_formula(hlt_formula, eta_c, pt_fine), color='darkorchid', linewidth=2.5, label='HLT card (generated)')

        extra = [s if s is not None else np.nan for s in data['sigma_extra_pt'][ie]]
        n_pairs = data['n_matched_pairs'][ie]
        rx, ry = step_edges(pt_edges, extra)
        ax.step(rx, ry, where='post', color='gray', linewidth=1.5, linestyle=':', label='raw extra smearing (data)')
        for ip in range(len(pt_edges) - 1):
            if n_pairs[ip] < min_pairs:
                ax.axvspan(pt_edges[ip], pt_edges[ip + 1], color='gray', alpha=0.08, linewidth=0)

        finish_panel(ax, eta_edges, ie, r'Particle $p_{T}$ [GeV]', logy=True)

    axes[0].set_ylabel(r'Relative $p_{T}$ resolution $\sigma(p_{T})/p_{T}$')
    fig.suptitle('{} momentum resolution'.format(cat), fontsize=15)
    save(fig, outdir, 'resolution_{}.png'.format(cat))


def plot_impact_parameter(curves, offline_text, hlt_text, formula_name, sigma_key, eta_edges, pt_edges, outdir,
                           min_pairs=200, ylabel=''):
    '''Plot one TrackSmearing resolution formula, d0 or dz, against its measured extra sigma.
    '''
    offline_formula = extract_formula_block(offline_text, 'TrackSmearing', formula_name)
    hlt_formula = extract_formula_block(hlt_text, 'TrackSmearing', formula_name)
    tip = curves['trackImpactParameter']
    ne = len(eta_edges) - 1
    pt_fine = fine_pt_grid(pt_edges)

    fig, axes = new_panel_figure(ne)
    for ie, ax in enumerate(axes):
        eta_c = 0.5 * (eta_edges[ie] + eta_edges[ie + 1])
        ax.plot(pt_fine, sample_formula(offline_formula, eta_c, pt_fine), color='dodgerblue', linewidth=2.5, label='offline card')
        ax.plot(pt_fine, sample_formula(hlt_formula, eta_c, pt_fine), color='darkorchid', linewidth=2.5, label='HLT card (generated)')

        extra = [s if s is not None else np.nan for s in tip[sigma_key][ie]]
        n_pairs = tip['n_pairs'][ie]
        rx, ry = step_edges(pt_edges, extra)
        ax.step(rx, ry, where='post', color='gray', linewidth=1.5, linestyle=':', label='raw extra smearing (data)')
        for ip in range(len(pt_edges) - 1):
            if n_pairs[ip] < min_pairs:
                ax.axvspan(pt_edges[ip], pt_edges[ip + 1], color='gray', alpha=0.08, linewidth=0)

        finish_panel(ax, eta_edges, ie, r'Particle $p_{T}$ [GeV]', logy=True)

    axes[0].set_ylabel(ylabel)
    fig.suptitle('Track impact parameter resolution ({})'.format(formula_name.replace('ResolutionFormula', '')), fontsize=15)
    save(fig, outdir, 'resolution_track{}.png'.format(formula_name.replace('ResolutionFormula', '')))


def plot_jet_energy_scale(curves, offline_text, hlt_text, eta_edges, jet_pt_edges, outdir, min_count=200):
    '''Plot the jet energy scale: offline and HLT formulas against the measured HLT/offline
    jet-pT ratio.
    '''
    offline_formula = extract_formula_block(offline_text, 'JetEnergyScalePUPPIAK8', 'ScaleFormula')
    hlt_formula = extract_formula_block(hlt_text, 'JetEnergyScalePUPPIAK8', 'ScaleFormula')
    jes = curves['jetEnergyScale']
    ne = len(eta_edges) - 1
    pt_fine = fine_pt_grid(jet_pt_edges)

    fig, axes = new_panel_figure(ne)
    for ie, ax in enumerate(axes):
        eta_c = 0.5 * (eta_edges[ie] + eta_edges[ie + 1])
        ax.plot(pt_fine, sample_formula(offline_formula, eta_c, pt_fine), color='dodgerblue', linewidth=2.5, label='offline card')
        ax.plot(pt_fine, sample_formula(hlt_formula, eta_c, pt_fine), color='darkorchid', linewidth=2.5, label='HLT card (generated)')

        ratio = [r if r is not None else np.nan for r in jes['scout_over_offline_ratio'][ie]]
        n_jets = jes['n_jets_scout_over_offline'][ie]
        rx, ry = step_edges(jet_pt_edges, ratio)
        ax.step(rx, ry, where='post', color='gray', linewidth=1.5, linestyle=':',
                label='raw data ratio (scoutfj_pt / fj_pt)')
        for ip in range(len(jet_pt_edges) - 1):
            if n_jets[ip] < min_count:
                ax.axvspan(jet_pt_edges[ip], jet_pt_edges[ip + 1], color='gray', alpha=0.08, linewidth=0)

        ax.axhline(1.0, color='black', linewidth=0.8, linestyle='-', alpha=0.3)
        finish_panel(ax, eta_edges, ie, r'Jet $p_{T}$ [GeV]')

    axes[0].set_ylabel('Jet energy scale factor')
    fig.suptitle('Jet energy scale (AK8 PUPPI)', fontsize=15)
    save(fig, outdir, 'scale_jetEnergyPUPPIAK8.png')


def main():
    '''Read the curves file and both cards, and write one figure per module.'''
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
    jet_pt_edges = curves['binning']['jet_pt_edges']

    with open(args.offline_card) as f:
        offline_text = f.read()
    with open(args.hlt_card) as f:
        hlt_text = f.read()

    os.makedirs(args.outdir, exist_ok=True)

    for cat, module in EFFICIENCY_MODULES.items():
        plot_efficiency(curves, offline_text, hlt_text, cat, module, eta_edges, pt_edges, args.outdir)

    for cat, module in RESOLUTION_MODULES.items():
        plot_pt_resolution(curves, offline_text, hlt_text, cat, module, eta_edges, pt_edges, args.outdir)

    plot_impact_parameter(curves, offline_text, hlt_text, 'D0ResolutionFormula', 'sigma_extra_dxy',
                           eta_edges, pt_edges, args.outdir, ylabel='dxy resolution [mm]')
    plot_impact_parameter(curves, offline_text, hlt_text, 'DZResolutionFormula', 'sigma_extra_dz',
                           eta_edges, pt_edges, args.outdir, ylabel='dz resolution [mm]')

    plot_jet_energy_scale(curves, offline_text, hlt_text, eta_edges, jet_pt_edges, args.outdir)


if __name__ == '__main__':
    main()
