# Dummy parameter set. CRAB formally requires a psetName even when JobType.scriptExe
# replaces "cmsRun pset.py" entirely, and it reads the OUTPUT FILE NAME from here to
# know what to collect - so 'ntuple.root' must stay in sync with what run_job.sh
# leaves in the job directory.
import FWCore.ParameterSet.Config as cms

process = cms.Process('JETCLASS')
process.source = cms.Source("EmptySource")
process.maxEvents = cms.untracked.PSet(input=cms.untracked.int32(-1))

# TFileService, NOT a PoolOutputModule. CRAB reads this pset at submit time to work
# out what the job produces, and a PoolOutputModule makes it classify ntuple.root as
# an EDM file (CRAB_EDMOutputFiles). It then tries to read a PSet hash out of it with
# `edmProvDump ntuple.root`, which aborts - our ntuple is a plain TTree written by the
# standalone FWLite ntuplizer and carries no EDM provenance. The job dies with exit
# code 56 after the work is done, exactly like the missing-FJR bug it replaced.
#
# A TFileService output IS a plain ROOT file, which is what we actually have, so CRAB
# classifies it as a TFile output, skips the provenance step and just stages it out.
# The name must stay in sync with what run_job.sh leaves in the job directory, and
# with the <AnalysisFile> entry run_job.sh writes into FrameworkJobReport.xml.
process.TFileService = cms.Service("TFileService",
                                   fileName=cms.string('ntuple.root'))

# CRAB cross-checks numCores against this at SUBMIT time and refuses the task if they
# disagree: "You specified config.JobType.numCores=2 ... but process.options.
# numberOfThreads=1". Rendered from the same --cores value as crab_config.py, so the
# two cannot drift apart. Nothing actually runs this pset - scriptExe replaces it - but
# the check happens anyway, before any job is created.
process.options = cms.untracked.PSet(
    numberOfThreads=cms.untracked.uint32(__CORES__),
    numberOfStreams=cms.untracked.uint32(0),
)
