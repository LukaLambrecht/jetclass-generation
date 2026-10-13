#!/bin/bash
# CRAB scriptExe. Runs ON the worker node, OUTSIDE any container, and hands over to
# run_job.sh, which dispatches each step into the container that step needs.
#
# It does NOT wrap everything in one container any more: the CMSSW chain needs EL7
# (CMSSW_10_6_30 is slc7), while the MadGraph5+Pythia8 generation for hepmc processes
# needs EL9 - the MG5 install is built against glibc 2.34 and will not even start under
# SLC7's 2.17. On lxplus this never shows, because run.sh generates on the host (EL9)
# and only enters the container for CMSSW; run_job.sh now reproduces that split.
set -u
echo "=== run_in_container.sh: args: $* ==="
echo "=== host: $(hostname)  site: ${GLIDEIN_CMSSite:-unknown}  os: $(grep -ho 'PRETTY_NAME=.*' /etc/os-release 2>/dev/null | head -1) ==="
chmod +x run_job.sh 2>/dev/null
./run_job.sh "$@" 2>&1 | tee -a job.log
exit ${PIPESTATUS[0]}
