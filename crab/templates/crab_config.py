# CRAB configuration, written by crab/build_simpack.py - edit the simpack's copy, not
# the template. Submit with ./crab_submit.sh from inside the simpack.
from CRABClient.UserUtilities import config

config = config()

config.General.workArea        = 'crab_logs'
config.General.requestName     = '__REQUESTNAME__'
config.General.transferOutputs = True
config.General.transferLogs    = __TRANSFERLOGS__

# PrivateMC: no input dataset, CRAB just makes __NJOBS__ jobs of __NEVENTS__ events.
config.Data.splitting     = 'EventBased'
config.Data.unitsPerJob   = __NEVENTS__
config.Data.totalUnits    = __TOTALUNITS__
config.Data.outLFNDirBase = '__OUTLFN__'
config.Data.publication   = False
config.Data.outputPrimaryDataset = '__PRIMARYDS__'
config.Data.outputDatasetTag     = '__DATASETTAG__'

config.JobType.pluginName  = 'PrivateMC'
# a formal requirement even though scriptExe replaces it; it is also where CRAB reads
# the output file name from - keep 'ntuple.root' in sync with run_job.sh
config.JobType.psetName    = 'pset.py'
config.JobType.scriptExe   = 'run_in_container.sh'
config.JobType.scriptArgs  = ['events=__NEVENTS__', 'batch=__BATCH__']
# What gets shipped to the worker node. For a production simpack this is run_job.sh
# plus the 'payload' DIRECTORY (chain configs, patches, ntuplizer sources - CRAB ships
# directories recursively). The site probe has no payload at all, so it must not ask
# for one: CRAB refuses to submit if a listed input file does not exist.
config.JobType.inputFiles  = __INPUTFILES__
config.JobType.outputFiles = ['ntuple.root']
# CRAB refuses a 1-core task above 3000 MB; measured peak usage is ~1.4 GB
config.JobType.maxMemoryMB    = __MEMORY__
config.JobType.maxJobRuntimeMin = __RUNTIMEMIN__
config.JobType.numCores    = __CORES__
# the chain writes several GB of intermediates (GEN-SIM, GEN-SIM-RAW, AODSIM) per batch
config.JobType.disableAutomaticOutputCollection = False

config.Site.storageSite = '__STORAGESITE__'
__WHITELIST__
