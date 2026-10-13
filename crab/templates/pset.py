# Dummy parameter set. CRAB formally requires a psetName even when JobType.scriptExe
# replaces "cmsRun pset.py" entirely, and it reads the OUTPUT FILE NAME from here to
# know what to collect - so 'ntuple.root' must stay in sync with what run_job.sh
# leaves in the job directory.
import FWCore.ParameterSet.Config as cms

process = cms.Process('JETCLASS')
process.source = cms.Source("EmptySource")
process.maxEvents = cms.untracked.PSet(input=cms.untracked.int32(-1))
process.output = cms.OutputModule("PoolOutputModule",
                                  fileName=cms.untracked.string('ntuple.root'))
process.out = cms.EndPath(process.output)
