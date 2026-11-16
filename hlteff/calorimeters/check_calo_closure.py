#!/usr/bin/env python3

'''Closure check for retuning ECal/HCal by degrading only their ResolutionFormula, holding
the zero-suppression thresholds at their offline values.

Delphes has no Efficiency module for neutral particles: "reconstructed or not" exists
only implicitly, as whatever fraction of the smeared energy clears the fixed
EnergyMin/EnergySignificanceMin. So resolution-only is not merely easier to measure
than a real efficiency curve, it is the only lever the module offers. The question here
is whether it is sufficient: does degrading the resolution by the amount measured in
real data predict a pass-rate matching the neutral efficiency measured directly in that
same data?

Per (category, |eta| bin, energy bin):
  1. combine the offline resolution in quadrature with the extra smearing measured for
     matched pairs in that bin;
  2. take the effective threshold as the larger of the absolute and the
     significance-scaled one;
  3. predict the efficiency as the Gaussian probability of clearing it;
  4. compare against the measured count ratio in the same bin.

This is a diagnostic, not a precision measurement: Delphes' own accept logic may
evaluate the significance against the post-smearing energy rather than the bin's, and
this uses each bin's centre energy rather than the distribution within it.

No Delphes card is modified; this only measures and reports.

Usage:
  python check_calo_closure.py [--curves PATH] [--offline-card PATH] [--outdir DIR]
'''

import os
import sys
import json
import math
import argparse

import numpy as np
import matplotlib.pyplot as plt

CALO_DIR = os.path.dirname(os.path.abspath(__file__))
HLTEFF_DIR = os.path.dirname(CALO_DIR)
REPO_DIR = os.path.dirname(HLTEFF_DIR)
sys.path.insert(0, HLTEFF_DIR)
from delphes_formula import evaluate_formula, extract_formula_block, extract_scalar
from generate_hlt_card import fill_missing

DEFAULT_CURVES = os.path.join(HLTEFF_DIR, 'curves_qcd.json')
DEFAULT_OFFLINE_CARD = os.path.join(REPO_DIR, 'delphes_cards', 'delphes_card_CMS_JetClassII_onlyFatJet.tcl')
DEFAULT_OUTDIR = os.path.join(CALO_DIR, 'plots')

# neutral category -> its SimpleCalorimeter module
CALO_MODULES = {
    'photon': 'ECal',
    'neutralHadron': 'HCal',
}

plt.rcParams.update({
    'font.size': 13,
    'axes.labelsize': 14,
    'xtick.labelsize': 12,
    'ytick.labelsize': 12,
    'legend.fontsize': 11,
})


def normal_cdf(x):
    '''Standard normal CDF.'''
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def predicted_efficiency(energy, combined_sigma, energy_min, sig_min):
    '''Probability that a Gaussian of the given width, centred on `energy`, clears the
    effective threshold.
    '''
    if combined_sigma <= 0:
        return 1.0 if energy > max(energy_min, 0) else 0.0
    threshold = max(energy_min, sig_min * combined_sigma)
    return 1.0 - normal_cdf((threshold - energy) / combined_sigma)


def main():
    '''Run the closure check over every category and bin, and report the comparison.'''
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--curves', default=DEFAULT_CURVES)
    parser.add_argument('--offline-card', default=DEFAULT_OFFLINE_CARD)
    parser.add_argument('--outdir', default=DEFAULT_OUTDIR)
    parser.add_argument('--min-count', type=int, default=200,
        help='minimum offline candidate count in a bin to trust its measured efficiency (default: 200)')
    parser.add_argument('--min-pairs', type=int, default=200,
        help='minimum matched-pair count in a bin to trust its resolution measurement (default: 200)')
    args = parser.parse_args()

    with open(args.curves) as f:
        curves = json.load(f)
    with open(args.offline_card) as f:
        offline_text = f.read()

    eta_edges = curves['binning']['eta_edges']
    energy_edges = curves['neutralCalorimeter']['energy_edges']
    ne, nE = len(eta_edges) - 1, len(energy_edges) - 1

    os.makedirs(args.outdir, exist_ok=True)

    for cat, module in CALO_MODULES.items():
        data = curves['neutralCalorimeter']['categories'][cat]
        resolution_formula = extract_formula_block(offline_text, module, 'ResolutionFormula')
        energy_min = extract_scalar(offline_text, module, 'EnergyMin')
        sig_min = extract_scalar(offline_text, module, 'EnergySignificanceMin')

        print('\n=== {} ({}): EnergyMin={:g}, EnergySignificanceMin={:g} ==='.format(
            cat, module, energy_min, sig_min))

        fig, axes = plt.subplots(1, ne, figsize=(7 * ne, 5.5), sharey=True)
        if ne == 1:
            axes = [axes]

        for ie in range(ne):
            eta_c = 0.5 * (eta_edges[ie] + eta_edges[ie + 1])
            print('  |eta| in [{:g},{:g}):'.format(eta_edges[ie], eta_edges[ie + 1]))
            print('    {:>14s} {:>8s} {:>10s} {:>10s} {:>10s}'.format(
                'energy [GeV]', 'n_off', 'measured', 'predicted', 'residual'))

            # resolve extra-sigma with the same fallback logic used to build the card
            sigmas, valid = [], []
            for ip in range(nE):
                n_pairs = data['n_matched_pairs'][ie][ip]
                sigma = data['sigma_extra_energy'][ie][ip]
                ok = (sigma is not None) and (n_pairs >= args.min_pairs)
                sigmas.append(sigma if ok else 0.0)
                valid.append(ok)
            filled_sigmas, _ = fill_missing(sigmas, valid)

            measured, predicted, energies = [], [], []
            for ip in range(nE):
                energy_c = 0.5 * (energy_edges[ip] + energy_edges[ip + 1])
                n_off = data['n_offline'][ie][ip]
                meas = data['efficiency_ratio'][ie][ip]

                offline_sigma = evaluate_formula(resolution_formula, energy=energy_c, eta=eta_c)
                combined_sigma = float(np.hypot(offline_sigma, filled_sigmas[ip]))
                pred = predicted_efficiency(energy_c, combined_sigma, energy_min, sig_min)

                energies.append(energy_c)
                predicted.append(pred)
                measured.append(meas if meas is not None else np.nan)

                if n_off >= args.min_count and meas is not None:
                    print('    {:>14.2f} {:>8d} {:>10.3f} {:>10.3f} {:>+10.3f}'.format(
                        energy_c, n_off, meas, pred, meas - pred))

            ax = axes[ie]
            ax.plot(energies, predicted, color='darkorchid', linewidth=2.5,
                     label='predicted (resolution-only model)')
            meas_x = [e for e, m, n in zip(energies, measured, data['n_offline'][ie]) if n >= args.min_count and not np.isnan(m)]
            meas_y = [m for m, n in zip(measured, data['n_offline'][ie]) if n >= args.min_count and not np.isnan(m)]
            ax.plot(meas_x, meas_y, 'o', color='dodgerblue', markersize=5, label='measured (data)')
            for ip in range(nE):
                if data['n_offline'][ie][ip] < args.min_count:
                    ax.axvspan(energy_edges[ip], energy_edges[ip + 1], color='gray', alpha=0.08, linewidth=0)

            ax.set_xscale('log')
            ax.set_ylim(0, 1.05)
            ax.set_xlabel('Particle energy [GeV]')
            ax.minorticks_on()
            ax.grid(True, which='major', linestyle='-', alpha=0.4)
            ax.grid(True, which='minor', linestyle=':', alpha=0.2)
            ax.set_title(r'${:g} < |\eta| \leq {:g}$'.format(eta_edges[ie], eta_edges[ie + 1]), fontsize=13)
            ax.legend(loc='best')

        axes[0].set_ylabel('Efficiency')
        fig.suptitle('{} ({}): measured vs. resolution-only-predicted efficiency'.format(cat, module), fontsize=14)
        fig.tight_layout()
        outpath = os.path.join(args.outdir, 'closure_calo_{}.png'.format(cat))
        fig.savefig(outpath, dpi=150)
        plt.close(fig)
        print('Saved', outpath)


if __name__ == '__main__':
    main()
