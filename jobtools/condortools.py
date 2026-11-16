###################################################################################
# functionality for making job description files for the condor submission system #
###################################################################################

# A condor job needs two ingredients: a job description (.txt) file and an
# executable. The functions here create an executable bash script and submit it
# via a generated job description.

import os
import sys
import subprocess

def makeUnique(fname):
    '''Make a file name unique by appending a number, e.g. test.txt -> test1.txt
    if test.txt already exists.'''
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
    '''Write the opening part of an executable bash script: set HOME (pass 'auto'
    to take it from the environment), source the shared CMS software, set up a
    CMSSW release, export a proxy, and cd back to the current directory.

    The caller appends the actual commands to the file afterwards.
    '''

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
    '''Create a job description txt file for a single job.

    exe may be any runnable script; argstring is one space-separated string of
    its arguments. For the job flavours see
    https://batchdocs.web.cern.ch/local/submit.html. concurrency_limits is a raw
    "<name>:<weight>" string bounding how many of these jobs run at once - see
    concurrency_limit_for_max_running().
    '''

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
    '''Submit a job description file as a condor job.'''

    # check if file exists
    fname = os.path.splitext(jobDescription)[0]+'.txt'
    if not os.path.exists(fname):
        print('ERROR: job description file {} not found'.format(fname))
        sys.exit()

    # Standard batch schedds cannot submit jobs whose executable, log or output
    # paths live on /eos; the EosSubmit schedds are needed instead, enabled by
    # loading this module first.
    # See https://batchdocs.web.cern.ch/local/eossubmit.html
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
    '''Submit a single command, given as one "executable + args" string, as one
    job.'''
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
    '''Run several similar commands as one cluster of jobs, one job per command.

    Every command must share the same executable and the same number of
    arguments; only the argument values may differ.
    '''

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
    '''Submit a list of commands as a single job, run one after another.

    The commands are arbitrary: they need not share an executable or an argument
    count.
    '''
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
    '''Submit several sets of commands, one job per set.

    commands is a list of lists of command strings; the commands are arbitrary.
    '''
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
    default quota, so picking a private name and asking for quota/N per job
    throttles to N without needing anything configured centrally.

    The crucial property, and why this is used rather than `max_materialize` or
    DAGMan's -maxjobs: the negotiator enforces it across all clusters sharing the
    name, and this repo submits one cluster per job.

    The quota is read from the pool rather than hardcoded, since a throttle that
    silently changes meaning when the admin retunes the default would be worse
    than no throttle.
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
        the file outright as soon as max_materialize is set.
      - ONE itemdata variable holding the whole argument string, rather than one
        submit variable per field, so any field may differ between jobs without
        per-field plumbing.

    max_materialize limits how many of the cluster's jobs EXIST in the queue at
    a time (idle + running), so it also caps how many run; the rest are created
    as earlier ones finish. max_idle instead keeps materializing while fewer
    than that many jobs sit idle, which bounds the queue footprint but NOT the
    number running.
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
