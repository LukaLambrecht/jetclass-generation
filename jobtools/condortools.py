###################################################################################
# functionality for making job description files for the condor submission system #
###################################################################################

# general use:
# two ingredients are needed for a condor job:
# - a job description (.txt) file
# - an executable
# the functions in this tool allow creating an executable bash script
# and its submission via a job description file

import os
import sys
import subprocess

def makeUnique(fname):
    ### make a file name unique by appending a number to it,
    # e.g. test.txt -> test1.txt (in case test.txt already exists)
    # todo: works for now, but find cleaner way to submit jobs in a loop...
    if not os.path.exists(fname): return fname
    [name,ext] = os.path.splitext(fname)
    app = 1
    while app < 2500:
        tryname = name+str(app)+ext
        if not os.path.exists(tryname): return tryname
        app += 1
    msg = 'ERROR ###: already 2500 files named {} exist.'.format(fname)
    msg += ' consider choosing more specific names, splitting in folders, etc.'
    raise Exception(msg)

def initJobScript(name, 
                  home=None,
                  cmssw_version=None,
                  proxy=None):
    ### initialize an executable bash script with:
    # - setting HOME environment variable
    #   note: use 'auto' to extract the HOME from os.environ
    # - sourcing the shared cms software
    # - setting correct cmssw release
    # - exporting proxy
    
    # parse filename
    name = os.path.splitext(name)[0]
    fname = name+'.sh'
    if os.path.exists(fname): os.system('rm {}'.format(fname))
    cwd = os.path.abspath(os.getcwd())
    # parse home
    if home=='auto': home = os.environ['HOME']
    # write script
    with open(fname,'w') as script:
	# write bash shebang
        script.write('#!/bin/bash\n')
	# write echo script name
        script.write("echo '###exename###: {}'\n".format(fname))
	# write export home
        if home is not None:
            script.write('export HOME={}\n'.format(home))
	# write sourcing of common software
        script.write('source /cvmfs/cms.cern.ch/cmsset_default.sh\n')
	# write setting correct cmssw release
        if cmssw_version is not None:
            script.write('cd {}\n'.format( os.path.join( cmssw_version,'src' ) ) )
            script.write('eval `scram runtime -sh`\n')
	# write export proxy
        if proxy is not None:
            script.write('export X509_USER_PROXY={}\n'.format( proxy ))
        script.write('cd {}\n'.format( cwd ) )
    # make executable
    os.system('chmod +x '+fname)
    print('initJobScript created {}'.format(fname))

def makeJobDescription(name, exe, argstring=None, 
                       stdout=None, stderr=None, log=None,
                       cpus=1, mem=1024, disk=10240, 
                       proxy=None, jobflavour=None, concurrency_limits=None):
    ### create a single job description txt file
    # note: exe can for example be a runnable bash script
    # note: argstring is a single string containing the arguments to exe (space-separated)
    # note: for job flavour: see here: https://batchdocs.web.cern.ch/local/submit.html
    # note: concurrency_limits is a raw "<name>:<weight>" string limiting how many
    #       of these jobs the negotiator lets RUN at the same time, across all
    #       clusters sharing that name - see concurrency_limit_for_max_running()
    
    # parse arguments
    name = os.path.splitext(name)[0]
    fname = name+'.txt'
    if os.path.exists(fname): os.system('rm {}'.format(fname))
    if stdout is None: stdout = name+'_out_$(ClusterId)_$(ProcId)'
    if stderr is None: stderr = name+'_err_$(ClusterId)_$(ProcId)'
    # note: EosSubmit schedds require the log to be shared per job cluster
    # (i.e. no $(ProcId) in the name) - see
    # https://batchdocs.web.cern.ch/troubleshooting/eos.html#eos-submit-schedds
    if log is None: log = name+'_log_$(ClusterId)'
    # write file
    with open(fname,'w') as f:
        f.write('executable = {}\n'.format(exe))
        if argstring is not None: f.write('arguments = "{}"\n\n'.format(argstring))
        f.write('output = {}\n'.format(stdout))
        f.write('error = {}\n'.format(stderr))
        f.write('log = {}\n\n'.format(log))
        f.write('request_cpus = {}\n'.format(cpus))
        f.write('request_memory = {}\n'.format(mem))
        f.write('request_disk = {}\n'.format(disk))
        if proxy is not None: 
            f.write('x509userproxy = {}\n'.format(proxy))
            f.write('use_x509userproxy = true\n\n')
        #f.write('should_transfer_files = yes\n\n') 
        # (not fully sure whether to put 'yes', 'no' or omit it completely)
        if jobflavour is not None:
            f.write('+JobFlavour = "{}"\n\n'.format(jobflavour))
        if concurrency_limits is not None:
            f.write('concurrency_limits = {}\n\n'.format(concurrency_limits))
        f.write('queue\n\n')
    print('makeJobDescription created {}'.format(fname))

def submitCondorJob(jobDescription):
    ### submit a job description file as a condor job

    # check if file exists
    fname = os.path.splitext(jobDescription)[0]+'.txt'
    if not os.path.exists(fname):
        print('ERROR: job description file {} not found'.format(fname))
        sys.exit()

    # standard batch schedds cannot submit jobs whose executable/log/output
    # paths live on /eos; the EosSubmit schedds are needed instead, enabled
    # by loading this module first (see https://batchdocs.web.cern.ch/local/eossubmit.html)
    modload = ''
    if os.path.abspath(fname).startswith('/eos'):
        modload = 'module load lxbatch/eossubmit; '

    # check if need to move to another directory
    jddir, fname = os.path.split(fname)
    if len(jddir) > 0: cmd = f'{modload}cd {jddir}; condor_submit {fname}'
    else: cmd = f'{modload}condor_submit {fname}'

    # run the condor_submit command
    os.system(cmd)

def submitCommandAsCondorJob(name, command, stdout=None, stderr=None, log=None,
                        cpus=1, mem=1024, disk=10240,
                        home=None,
                        proxy=None, 
                        cmssw_version=None,
                        jobflavour=None):
    ### submit a single command as a single job
    # command is a string representing a single command (executable + args)
    submitCommandsAsCondorJobs(name, [[command]], stdout=stdout, stderr=stderr, log=log,
            cpus=cpus, mem=mem, disk=disk,
            home=home,
            proxy=proxy,
            cmssw_version=cmssw_version,
            jobflavour=jobflavour)

def submitCommandsAsCondorCluster(name, commands, stdout=None, stderr=None, log=None,
                        cpus=1, mem=1024, disk=10240,
                        home=None,
                        proxy=None,
                        cmssw_version=None,
                        jobflavour=None):
    ### run several similar commands within a single cluster of jobs
    # note: each command must have the same executable and number of args, only args can differ!
    # note: commands can be a list of commands (-> a job will be submitted for each command)
    
    # parse arguments
    name = os.path.splitext(name)[0]
    shname = makeUnique(name+'.sh')
    jdname = name+'.txt'
    [exe,argstring] = commands[0].split(' ',1) # exe must be the same for all commands
    nargs = len(argstring.split(' ')) # nargs must be the same for all commands
    # first make the executable
    initJobScript(shname, home=home, cmssw_version=cmssw_version, proxy=proxy)
    with open(shname,'a') as script:
        script.write(exe)
        script.write(' $@')
        script.write('\n')
    # then make the job description
    # first job:
    makeJobDescription(name,shname,argstring=argstring,stdout=stdout,stderr=stderr,log=log,
                       cpus=cpus,mem=mem,disk=disk,proxy=proxy,
                       jobflavour=jobflavour)
    # add other jobs:
    with open(jdname,'a') as script:
        for command in commands[1:]:
            [thisexe,thisargstring] = command.split(' ',1)
            thisnargs = len(thisargstring.split(' '))
            if( thisexe!=exe or thisnargs!=nargs):
                print('### ERROR ###: commands are not compatible to put in same cluster')
                return
            script.write('arguments = "{}"\n'.format(thisargstring))
            script.write('queue\n\n')
    # finally submit the job
    submitCondorJob(jdname)

def submitCommandsAsCondorJob(name, commands, stdout=None, stderr=None, log=None,
                        cpus=1, mem=1024, disk=10240, 
                        home=None,
                        proxy=None,
                        cmssw_version=None,
                        jobflavour=None,
                        concurrency_limits=None):
    ### submit a set of commands as a single job
    # commands is a list of strings, each string represents a single command (executable + args)
    # the commands can be anything and are not necessarily same executable or same number of args.
    submitCommandsAsCondorJobs(name, [commands], stdout=stdout, stderr=stderr, log=log,
                        cpus=cpus, mem=mem, disk=disk, 
                        home=home,
                        proxy=proxy,
                        cmssw_version=cmssw_version,
                        jobflavour=jobflavour,
                        concurrency_limits=concurrency_limits)

def submitCommandsAsCondorJobs(name, commands, stdout=None, stderr=None, log=None,
            cpus=1, mem=1024, disk=10240,
            home=None,
            proxy=None,
            cmssw_version=None,
            jobflavour=None,
            concurrency_limits=None):
    ### submit multiple sets of commands as jobs (one job per set)
    # commands is a list of lists of strings, each string represents a single command
    # the commands can be anything and are not necessarily same executable or number of args.
    for commandset in commands:
        # parse arguments
        name = os.path.splitext(name)[0]
        shname = makeUnique(name+'.sh')
        jdname = name+'.txt'
        # first make the executable
        initJobScript(shname, home=home, cmssw_version=cmssw_version, proxy=proxy)
        with open(shname,'a') as script:
             for cmd in commandset: script.write(cmd+'\n')
        # then make the job description
        makeJobDescription(name,shname,stdout=stdout,stderr=stderr,log=log,
                            cpus=cpus,mem=mem,disk=disk,proxy=proxy,
                            jobflavour=jobflavour,concurrency_limits=concurrency_limits)
        # finally submit the job
        submitCondorJob(jdname)


def concurrency_limit_for_max_running(max_running, name, quota=None):
    '''Build the `concurrency_limits` string that lets at most `max_running` of
    these jobs RUN simultaneously.

    HTCondor has no "max running jobs" submit knob. What it does have is
    concurrency limits: the negotiator gives every named limit a total quota and
    each job consumes a weight of it, so the number of jobs running at once is
    floor(quota / weight). A limit the pool admin has not defined gets the
    default quota (CONCURRENCY_LIMIT_DEFAULT, 2308032 on lxbatch), so picking a
    private name and asking for quota/N per job throttles to N without needing
    anything configured centrally.

    The crucial property, and why this is used here rather than
    `max_materialize` or DAGMan's -maxjobs: the negotiator enforces it across
    ALL clusters sharing the name, and this repo submits one cluster per job.
    (Verified on lxbatch: 6 jobs in 3 clusters with a weight for 2 -> exactly 2
    running, 4 idle.)

    The quota is read from the pool rather than hardcoded, since a throttle that
    silently changes meaning if the admin retunes CONCURRENCY_LIMIT_DEFAULT would
    be worse than no throttle.
    '''
    if max_running is None or max_running <= 0:
        return None
    if quota is None:
        try:
            out = subprocess.check_output(['condor_config_val', 'CONCURRENCY_LIMIT_DEFAULT'],
                                          stderr=subprocess.STDOUT)
            quota = int(out.decode().strip())
        except Exception as e:
            raise Exception(
                'could not read CONCURRENCY_LIMIT_DEFAULT from the condor configuration'
                ' ({}), so --max-running cannot be translated into a concurrency limit.'
                ' Pass the quota explicitly or drop --max-running.'.format(e))
    weight = quota // max_running
    if weight < 1:
        raise Exception('--max-running {} exceeds the concurrency quota {}'.format(max_running, quota))
    effective = quota // weight
    return '{}:{}'.format(name, weight), effective


def makeClusterJobDescription(name, exe, arglists,
                              stdout=None, stderr=None, log=None,
                              cpus=1, mem=1024, disk=10240,
                              proxy=None, jobflavour=None, concurrency_limits=None,
                              max_materialize=None, max_idle=None):
    '''Create a job description for ONE cluster holding one job per entry of `arglists`.

    Each entry of arglists is the complete, space-separated argument string for
    one job. Two deliberate differences from submitCommandsAsCondorCluster():

      - a SINGLE queue statement with an itemdata list, instead of a repeated
        "arguments = ...; queue" pair per job. That is required for late
        materialization: with repeated queue statements, condor_submit refuses
        the file outright ("Failed to parse command file") as soon as
        max_materialize is set.
      - ONE itemdata variable holding the whole argument string, rather than one
        submit variable per field, so any field may differ between jobs without
        per-field plumbing (and without depending on how HTCondor splits
        multi-variable itemdata).

    max_materialize limits how many of the cluster's jobs EXIST in the queue at
    a time (idle + running), so it also caps how many run; the rest are created
    as earlier ones finish. max_idle instead keeps materializing while fewer
    than that many jobs sit idle, which bounds the queue footprint but NOT the
    number running. Both verified on lxbatch (HTCondor 25.0): a 6-job cluster
    with max_materialize = 2 reports TotalSubmitProcs = 6 with 2 procs present.
    '''
    name = os.path.splitext(name)[0]
    fname = name+'.txt'
    if os.path.exists(fname): os.system('rm {}'.format(fname))
    if stdout is None: stdout = name+'_out_$(ClusterId)_$(ProcId)'
    if stderr is None: stderr = name+'_err_$(ClusterId)_$(ProcId)'
    # note: EosSubmit schedds require the log to be shared per job cluster
    # (i.e. no $(ProcId) in the name) - see
    # https://batchdocs.web.cern.ch/troubleshooting/eos.html#eos-submit-schedds
    if log is None: log = name+'_log_$(ClusterId)'
    for args in arglists:
        if '\n' in args or '\r' in args:
            raise Exception('argument string contains a newline, which cannot go in an'
                            ' itemdata list: {!r}'.format(args))
    with open(fname,'w') as f:
        f.write('executable = {}\n'.format(exe))
        f.write('arguments = "$(args)"\n\n')
        f.write('output = {}\n'.format(stdout))
        f.write('error = {}\n'.format(stderr))
        f.write('log = {}\n\n'.format(log))
        f.write('request_cpus = {}\n'.format(cpus))
        f.write('request_memory = {}\n'.format(mem))
        f.write('request_disk = {}\n'.format(disk))
        if proxy is not None:
            f.write('x509userproxy = {}\n'.format(proxy))
            f.write('use_x509userproxy = true\n')
        if jobflavour is not None:
            f.write('+JobFlavour = "{}"\n'.format(jobflavour))
        if concurrency_limits is not None:
            f.write('concurrency_limits = {}\n'.format(concurrency_limits))
        if max_materialize is not None:
            f.write('max_materialize = {}\n'.format(max_materialize))
        if max_idle is not None:
            f.write('max_idle = {}\n'.format(max_idle))
        f.write('\n')
        f.write('queue args from (\n')
        for args in arglists:
            f.write('{}\n'.format(args))
        f.write(')\n')
    print('makeClusterJobDescription created {} ({} job(s) in one cluster)'.format(
        fname, len(arglists)))


def submitArgsAsCondorCluster(name, exe, arglists, prelude=None, epilogue=None,
                              stdout=None, stderr=None, log=None,
                              cpus=1, mem=1024, disk=10240,
                              home=None, proxy=None, cmssw_version=None,
                              jobflavour=None, concurrency_limits=None,
                              max_materialize=None, max_idle=None):
    '''Submit ONE cluster that runs `exe` once per entry of `arglists`.

    `prelude`/`epilogue` are lists of shell lines run before/after the executable
    inside the generated wrapper script (e.g. a cd, markers, extra exports). The
    executable itself is invoked as `exe "$@"`, so the per-job arguments come
    from the submit file rather than being baked into the script - which is what
    lets all the jobs share one cluster.
    '''
    name = os.path.splitext(name)[0]
    shname = makeUnique(name+'.sh')
    initJobScript(shname, home=home, cmssw_version=cmssw_version, proxy=proxy)
    with open(shname,'a') as script:
        for line in (prelude or []): script.write(line+'\n')
        script.write('{} "$@"\n'.format(exe))
        for line in (epilogue or []): script.write(line+'\n')
    makeClusterJobDescription(name, shname, arglists,
                              stdout=stdout, stderr=stderr, log=log,
                              cpus=cpus, mem=mem, disk=disk, proxy=proxy,
                              jobflavour=jobflavour, concurrency_limits=concurrency_limits,
                              max_materialize=max_materialize, max_idle=max_idle)
    submitCondorJob(name+'.txt')
