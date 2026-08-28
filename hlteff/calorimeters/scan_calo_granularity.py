#!/usr/bin/env python3

'''
Test whether coarsening HCal's tower grid (see calo_grid.py) can reproduce
the real offline-to-scouting neutral-hadron multiplicity reduction seen in
data - i.e. whether "online clustering merges what offline resolves
separately" is well modeled simply by using bigger towers online.

This needs no Delphes run and no per-particle matching: it's a purely
geometric effect, so it can be tested directly against real candidate
positions already in the ntuples. For a range of integer coarsening
factors N (the tower grid's eta/phi edges downsampled by N - see
calo_grid.coarsen_regions):
  1. Take real OFFLINE neutralHadron candidates (npfcand_isNeutralHad),
     assign each to a tower of the N-coarsened HCal grid, and sum the
     energy of candidates sharing a tower within the same jet - simulating
     what SimpleCalorimeter would output as a *single* candidate for that
     tower, however many true candidates actually landed there.
  2. Bin the resulting per-jet "merged pseudo-candidate" energies the same
     way as derive_curves.py's neutralCalorimeter measurement (average
     count per jet per energy bin).
  3. Compare that predicted spectrum to the *real* scouting neutralHadron
     spectrum (scoutpfcand_isNeutralHad) - not a resolution/threshold model
     this time, just "does merging alone get the shape right".

Reports a goodness-of-fit ranking across the scanned N and saves a
comparison plot. Simplification: uses a single inclusive |eta|<2.5 sample
(no barrel/endcap split) to keep this scan fast and its output a single,
directly actionable answer - see README for the follow-up once an N is
chosen. Does not modify any Delphes card.

Usage:
  python scan_calo_granularity.py [--factors 1,2,3,4,6,8,12,16,20] [--max-jets 20000]
'''

import os
import sys
import glob
import argparse
import time

import numpy as np
import awkward as ak
import uproot
import matplotlib.pyplot as plt

CALO_DIR = os.path.dirname(os.path.abspath(__file__))
HLTEFF_DIR = os.path.dirname(CALO_DIR)
REPO_DIR = os.path.dirname(HLTEFF_DIR)
sys.path.insert(0, HLTEFF_DIR)
from calo_grid import parse_regions, coarsen_regions, assign_towers
from binning import PT_EDGES  # reused as the energy grid, same as derive_curves.py

DEFAULT_INPUT_DIR = '/eos/cms/store/cmst3/group/vhcc/ScoutingAK8/2024/train/QCD_PT-mixed_TuneCP5_13p6TeV_pythia8_new'
DEFAULT_OFFLINE_CARD = os.path.join(REPO_DIR, 'delphes_cards', 'delphes_card_CMS_JetClassII_onlyFatJet.tcl')
DEFAULT_OUTDIR = os.path.join(CALO_DIR, 'plots')

BRANCHES = [
    'fj_isQCD', 'fj_eta', 'fj_phi', 'scoutfj_eta', 'scoutfj_phi',
    'npfcand_etarel', 'npfcand_phirel', 'npfcand_energy', 'npfcand_isNeutralHad',
    'scoutpfcand_etarel', 'scoutpfcand_phirel', 'scoutpfcand_energy', 'scoutpfcand_isNeutralHad',
]

plt.rcParams.update({
    'font.size': 13,
    'axes.labelsize': 14,
    'xtick.labelsize': 12,
    'ytick.labelsize': 12,
    'legend.fontsize': 11,
})


def wrap_phi(phi):
    return (phi + np.pi) % (2 * np.pi) - np.pi


def spectrum_from_energies(energy_lists, n_jets, energy_edges):
    ### average number of candidates per jet per energy bin, from a list of
    # per-jet numpy arrays of candidate energies
    flat = np.concatenate(energy_lists) if energy_lists else np.array([])
    counts, _ = np.histogram(flat, bins=energy_edges)
    return counts / max(n_jets, 1)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--input-dir', default=DEFAULT_INPUT_DIR)
    parser.add_argument('--offline-card', default=DEFAULT_OFFLINE_CARD)
    parser.add_argument('--n-files', type=int, default=1)
    parser.add_argument('--max-jets', type=int, default=20000,
        help='keep this small - the question this answers doesn\'t need much statistics (default: 20000)')
    parser.add_argument('--chunk-size', type=int, default=20000)
    parser.add_argument('--factors', default='1,2,3,4,6,8,12,16,20',
        help='comma-separated tower-grid coarsening factors to scan (default: 1,2,3,4,6,8,12,16,20)')
    parser.add_argument('--outdir', default=DEFAULT_OUTDIR)
    args = parser.parse_args()

    factors = [int(x) for x in args.factors.split(',')]

    offline_text = open(args.offline_card).read()
    base_regions = parse_regions(offline_text, 'HCal')
    grids = {f: coarsen_regions(base_regions, f) for f in factors}

    files = sorted(glob.glob(os.path.join(args.input_dir, 'dnnTuples_nanov15_*.root')))[:args.n_files]
    if not files:
        raise SystemExit('no dnnTuples_nanov15_*.root files found in {}'.format(args.input_dir))
    print('Reading {} file(s), up to {} jets:'.format(len(files), args.max_jets))
    for fn in files:
        print('  ', fn)

    offline_energies = []       # raw npfcand energies (unmerged reference)
    scout_energies = []         # real scoutpfcand energies (the target)
    merged_energies = {f: [] for f in factors}  # per-jet merged-pseudo-candidate energies, per factor

    n_jets_done = 0
    t0 = time.time()
    stop = False
    for fn in files:
        if stop:
            break
        with uproot.open(fn) as f:
            tree = f['tree']
            for chunk in tree.iterate(BRANCHES, step_size=args.chunk_size, library='ak'):
                chunk = chunk[chunk['fj_isQCD'] == 1]
                n_jets_chunk = len(chunk)
                if n_jets_chunk == 0:
                    continue

                fj_eta = ak.to_numpy(chunk['fj_eta'])
                fj_phi = ak.to_numpy(chunk['fj_phi'])
                scoutfj_eta = ak.to_numpy(chunk['scoutfj_eta'])
                scoutfj_phi = ak.to_numpy(chunk['scoutfj_phi'])

                for j in range(n_jets_chunk):
                    off_mask = np.asarray(chunk['npfcand_isNeutralHad'][j]) != 0
                    off_eta = fj_eta[j] + np.asarray(chunk['npfcand_etarel'][j], dtype=np.float64)[off_mask]
                    off_phi = wrap_phi(fj_phi[j] + np.asarray(chunk['npfcand_phirel'][j], dtype=np.float64))[off_mask]
                    off_energy = np.asarray(chunk['npfcand_energy'][j], dtype=np.float64)[off_mask]

                    scout_mask = np.asarray(chunk['scoutpfcand_isNeutralHad'][j]) != 0
                    scout_energy = np.asarray(chunk['scoutpfcand_energy'][j], dtype=np.float64)[scout_mask]

                    offline_energies.append(off_energy)
                    scout_energies.append(scout_energy)

                    if len(off_energy) == 0:
                        continue
                    for factor in factors:
                        tower_id = assign_towers(grids[factor], off_eta, off_phi)
                        valid = tower_id >= 0
                        if not np.any(valid):
                            continue
                        # sum energy of candidates sharing a tower -> one merged pseudo-candidate each
                        uniq, inv = np.unique(tower_id[valid], return_inverse=True)
                        merged = np.zeros(len(uniq))
                        np.add.at(merged, inv, off_energy[valid])
                        merged_energies[factor].append(merged)

                n_jets_done += n_jets_chunk
                print('  processed {} jets ({:.1f} jets/s)'.format(n_jets_done, n_jets_done / max(time.time() - t0, 1e-9)))
                if n_jets_done >= args.max_jets:
                    stop = True
                    break

    print('Total jets processed: {} in {:.1f}s'.format(n_jets_done, time.time() - t0))

    offline_spectrum = spectrum_from_energies(offline_energies, n_jets_done, PT_EDGES)
    scout_spectrum = spectrum_from_energies(scout_energies, n_jets_done, PT_EDGES)
    predicted = {f: spectrum_from_energies(merged_energies[f], n_jets_done, PT_EDGES) for f in factors}

    # goodness-of-fit vs the real scouting target, in bins with enough
    # offline statistics to be meaningful (log-space residuals, since the
    # spectrum spans orders of magnitude)
    well_populated = offline_spectrum * n_jets_done >= 50
    eps = 1e-6
    scores = {}
    for f in factors:
        resid = np.log(predicted[f][well_populated] + eps) - np.log(scout_spectrum[well_populated] + eps)
        scores[f] = float(np.sqrt(np.mean(resid ** 2)))

    print('\nGoodness-of-fit (RMS log-residual vs real scouting spectrum, lower is better):')
    for f in sorted(factors, key=lambda f: scores[f]):
        print('  factor {:3d}: {:.4f}'.format(f, scores[f]))
    best = min(factors, key=lambda f: scores[f])
    print('\nBest-fit coarsening factor: {}'.format(best))

    # plot
    energy_c = 0.5 * (np.asarray(PT_EDGES[:-1]) + np.asarray(PT_EDGES[1:]))
    fig, ax = plt.subplots(figsize=(9, 6.5))
    ax.step(energy_c, offline_spectrum, where='mid', color='dodgerblue', linewidth=2.5, label='offline (raw)')
    ax.step(energy_c, scout_spectrum, where='mid', color='darkorange', linewidth=2.5, label='scouting (real, target)')
    cmap = plt.get_cmap('plasma')
    for i, f in enumerate(sorted(factors)):
        color = cmap(0.15 + 0.7 * i / max(len(factors) - 1, 1))
        lw = 3.0 if f == best else 1.3
        ls = '-' if f == best else '--'
        label = 'merged, factor {}{}'.format(f, ' (best fit)' if f == best else '')
        ax.step(energy_c, predicted[f], where='mid', color=color, linewidth=lw, linestyle=ls, label=label)

    ax.set_xscale('log')
    ax.set_yscale('log')
    ax.set_xlabel('Particle energy [GeV]')
    ax.set_ylabel('Average number of neutral hadrons / jet / bin')
    ax.minorticks_on()
    ax.grid(True, which='major', linestyle='-', alpha=0.4)
    ax.grid(True, which='minor', linestyle=':', alpha=0.2)
    ax.legend(fontsize=9, ncol=2)
    fig.tight_layout()

    os.makedirs(args.outdir, exist_ok=True)
    outpath = os.path.join(args.outdir, 'scan_calo_granularity_HCal.png')
    fig.savefig(outpath, dpi=150)
    print('Saved', outpath)


if __name__ == '__main__':
    main()
