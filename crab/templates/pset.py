# Dummy parameter set. CRAB requires a psetName even when JobType.scriptExe replaces
# "cmsRun pset.py" entirely, and it reads the output file name from here to know what
# to collect - so 'ntuple.root' must stay in sync with what run_job.sh leaves behind.
import FWCore.ParameterSet.Config as cms

process = cms.Process('JETCLASS')
process.source = cms.Source("EmptySource")
process.maxEvents = cms.untracked.PSet(input=cms.untracked.int32(-1))

# A TFileService, not a PoolOutputModule. CRAB reads this pset at submit time to
# work out what the job produces, and a PoolOutputModule would classify ntuple.root
# as an EDM file. CRAB then tries to read a PSet hash out of it with `edmProvDump`,
# which aborts, because the ntuple is a plain TTree with no EDM provenance - and the
# job dies with exit code 56 once all the work is done.
#
# A TFileService output is a plain ROOT file, which is what this actually is, so CRAB
# skips the provenance step and simply stages it out. The name must stay in sync both
# with what run_job.sh leaves behind and with the <AnalysisFile> entry it writes into
# FrameworkJobReport.xml.
process.TFileService = cms.Service("TFileService",
                                   fileName=cms.string('ntuple.root'))

# CRAB cross-checks numCores against this at submit time and refuses the task if the
# two disagree. Rendered from the same --cores value as crab_config.py, so they
# cannot drift apart. Nothing runs this pset, but the check happens regardless,
# before any job is created.
process.options = cms.untracked.PSet(
    numberOfThreads=cms.untracked.uint32(__CORES__),
    numberOfStreams=cms.untracked.uint32(0),
)
