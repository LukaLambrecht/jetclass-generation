#!/bin/bash
# CRAB scriptExe. Runs ON the worker node, OUTSIDE any container, and hands over to
# run_job.sh, which dispatches each step into the container that step needs.
#
# The steps cannot share one container: the CMSSW chain needs EL7, while the
# MadGraph5+Pythia8 generation needs EL9, since the MG5 install is built against a
# newer glibc than SLC7 provides. run_job.sh keeps the two apart.
set -u
echo "=== run_in_container.sh: args: $* ==="
echo "=== host: $(hostname)  site: ${GLIDEIN_CMSSite:-unknown}  os: $(grep -ho 'PRETTY_NAME=.*' /etc/os-release 2>/dev/null | head -1) ==="
chmod +x run_job.sh 2>/dev/null
./run_job.sh "$@" 2>&1 | tee -a job.log
exit ${PIPESTATUS[0]}
