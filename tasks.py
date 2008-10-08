#!/usr/bin/python

"""
Task base class for the Ecoconnect Controller.

A "task" represents a particular group of external jobs, for a single
reference time, that we want separate scheduling control over (as a
group).  Each task has certain prerequisites that must be satisfied
before it can launch its external task, and certain postrequisites that
are created or achieved as the task runs, and which may be prerequisites
for other tasks.  A task must maintain an accurate representation of
the task's state as it follows through to the end of processing for its
reference time.  

tasks communicate with each other in order to sort out inter-task
dependencies (i.e. match postrequisites with prerequisites).

Task names must not contain underscores at the moment (the 'name'
attribute, not the class name itself, that is).
"""

import reference_time
from requisites import requisites, fuzzy_requisites
from time import sleep

import os
import re
import sys
from copy import deepcopy
from time import strftime
import Pyro.core

import logging
import logging.handlers

#----------------------------------------------------------------------
class task_base( Pyro.core.ObjBase ):
    "ecoconnect task base class"
    
    name = "task base class"

    def __init__( self, ref_time, initial_state ):

        Pyro.core.ObjBase.__init__(self)

        # adjust ref time (needed for creation of initial task list)
        self.ref_time = self.nearest_ref_time( ref_time )

        self.log = logging.getLogger( "main." + self.name ) 

        self.latest_message = ""
        self.abdicated = False # True => my successor has been created

        self.estimated_run_time = 30  # minutes

        self.prerequisites = requisites( self.name, [] )
        self.postrequisites = requisites( self.name, [] )

        # initial states: waiting, running, finished
        if not initial_state:
            self.state = "waiting"
            pass
        elif initial_state == "waiting": 
            self.state = "waiting"
        elif initial_state == "finished":  
            self.postrequisites.set_all_satisfied()
            self.log.warning( self.identity() + " starting in FINISHED state" )
            self.state = "finished"
        elif initial_state == "ready":
            # waiting, but ready to go
            self.state = "waiting"
            self.log.warning( self.identity() + " starting in READY state" )
            self.prerequisites.set_all_satisfied()
        else:
            self.log.critical( "unknown initial task state: " + initial_state )
            sys.exit(1)

    def nearest_ref_time( self, rt ):
        # return the next time >= rt for which this task is valid
        rh = int( rt[8:10])
        
        incr = None

        first_vh = self.valid_hours[ 0 ]
        extra_vh = 24 + first_vh 
        foo = self.valid_hours
        foo.append( extra_vh )

        for vh in foo:
            if rh <= vh:
                incr = vh - rh
                break
    
        nearest_rt = reference_time.increment( rt, incr )
        return nearest_rt


    def next_ref_time( self ):
        # return the next time that this task is valid at
        n_times = len( self.valid_hours )
        if n_times == 1:
            increment = 24
        else:
            i_now = self.valid_hours.index( int( self.ref_time[8:10]) )
            # list indices start at zero
            if i_now < n_times - 1 :
                increment = self.valid_hours[ i_now + 1 ] - self.valid_hours[ i_now ]
            else:
                increment = self.valid_hours[ 0 ] + 24 - self.valid_hours[ i_now ]

        return reference_time.increment( self.ref_time, increment )


    def run_if_ready( self, tasks, dummy_clock_rate ):

        # don't run if any previous instance not finished
        for task in tasks:
            if task.name == self.name:
                if task.state != "finished":
                    if int( task.ref_time ) < int( self.ref_time ):
                        self.log.debug( self.identity() + " blocked by " + task.identity() )
                        return

        if self.state == "finished":
            # already finished
            pass
        elif self.state == "running":
            # already running
            pass
        elif self.prerequisites.all_satisfied():
            # prerequisites all satisified, so run me
            if dummy_clock_rate:
                # we're in dummy mode
                self.run_external_dummy( dummy_clock_rate )
            else:
                self.run_external_task()
        else:
            # still waiting
            pass

    def run_external_dummy( self, dummy_clock_rate ):
        # RUN THE EXTERNAL TASK AS A SEPARATE PROCESS
        self.log.info( "launching external dummy for " + self.ref_time )
        os.system( "./task_dummy.py " + self.name + " " + self.ref_time + " " + str(dummy_clock_rate) + " &" )
        self.state = "running"

    def run_external_task( self ):
        # DERIVED CLASSES MUST OVERRIDE THIS METHOD TO RUN THE EXTERNAL
        # TASK, AND SET self.state = "running"
        self.log.critical( "task base class run() should not be called" )
        return

    def get_state( self ):
        return self.name + ": " + self.state

    def get_estimated_run_time( self ):
        return self.estimated_run_time

    def identity( self ):
        return self.name + "%" + self.ref_time

    def display( self ):
        return self.name + "(" + self.ref_time + ")"

    def set_finished( self ):
        # could do this automatically off the "name finished for ref_time" message
        self.state = "finished"

    def abdicate( self ):
        if self.state == "finished" and not self.abdicated:
            self.abdicated = True
            return True
        else:
            return False

    def get_satisfaction( self, tasks ):

        for task in tasks:
            self.prerequisites.satisfy_me( task.postrequisites )

    def will_get_satisfaction( self, tasks ):
        temp_prereqs = deepcopy( self.prerequisites )
        for task in tasks:
            temp_prereqs.will_satisfy_me( task.postrequisites )
    
        if not temp_prereqs.all_satisfied(): 
            return False
        else:
            return True

    def is_complete( self ):  # not needed?
        if self.postrequisites.all_satisfied():
            return True
        else:
            return False

    def is_running( self ): 
        if self.state == "running":
            return True
        else:
            return False

    def is_finished( self ): 
        if self.state == "finished":
            return True
        else:
            return False

    def get_postrequisite_list( self ):
        return self.postrequisites.get_list()

    def get_postrequisites( self ):
        return self.postrequisites.get_requisites()

    def get_latest_message( self ):
        return self.latest_message

    def get_valid_hours( self ):
        return self.valid_hours

    def incoming( self, priority, message ):
        # receive all incoming pyro messages for this task 

        self.latest_message = message

        if self.state != "running":
            # message from a task that's not supposed to be running
            self.log.warning( "MESSAGE FROM NON-RUNNING TASK: " + message )

        if self.postrequisites.requisite_exists( message ):
            # an expected postrequisite from a running task
            if self.postrequisites.is_satisfied( message ):
                self.log.warning( "POSTREQUISITE ALREADY SATISFIED: " + message )

            self.log.info( message )
            self.postrequisites.set_satisfied( message )

        else:
            # a non-postrequisite message, e.g. progress report
            if priority == "NORMAL":
                self.log.info( message )
            elif priority == "WARNING":
                self.log.warning( message )
            elif priority == "CRITICAL":
                self.log.critical( message )
            else:
                self.log.warning( message )

#----------------------------------------------------------------------
class runahead_task_base( task_base ):
    # for tasks with no-prerequisites, e.g. downloader and nztide,
    # that would otherwise run ahead indefinitely: delay if we get
    # "too far ahead" based on number of existing finished tasks.

    def __init__( self, ref_time, initial_state = "waiting" ):

        task_base.__init__( self, ref_time, initial_state )

        self.MAX_FINISHED = 4
        self.log.info( self.identity() + " max runahead: " + str( self.MAX_FINISHED ) + " tasks" )

    def run_if_ready( self, tasks, dummy_clock_rate ):
        # don't run if too many previous finished instances exist
        delay = False

        old_and_finished = []
        if self.state == "waiting":
            for task in tasks:
               if task.name == self.name and task.state == "finished":
                   old_and_finished.append( task.ref_time )
                            
            if len( old_and_finished ) >= self.MAX_FINISHED:
                delay = True

        if delay:
            # the following gets logged every time the function is called
            # self.log.debug( self.identity() + " ready and waiting (too far ahead)" )
            pass

        else:
            task_base.run_if_ready( self, tasks, dummy_clock_rate )

#----------------------------------------------------------------------
class downloader( runahead_task_base ):
    "Met Office input file download task"

    """
    This task provides initial input to get things going: it starts
    running immediately and it completes when its outputs are ready
    for use by downstream tasks.
    """

    name = "downloader"
    valid_hours = [ 0, 6, 12, 18 ]

    def __init__( self, ref_time, initial_state = "waiting" ):
        
        runahead_task_base.__init__( self, ref_time, initial_state )

        hour = ref_time[8:10]

        self.estimated_run_time = 10

        # no prerequisites: this is The Initial Task
        self.prerequisites = requisites( self.name, [])

        lbc_06 = reference_time.decrement( ref_time, 6 )
        lbc_12 = reference_time.decrement( ref_time, 12 )

        self.estimated_run_time = 1

        if hour == "00":

            self.postrequisites = requisites( self.name, [ 
                    self.name + " started for " + ref_time,
                    "file obstore_" + ref_time + ".um ready",
                    "file bgerr" + ref_time + ".um ready", 
                    "file lbc_" + lbc_12 + ".um ready", 
                    "file 10mwind_" + ref_time + ".um ready",
                    "file seaice_" + ref_time + ".um ready",
                    self.name + " finished for " + ref_time
                    ])

        elif hour == "12":

            self.postrequisites = requisites( self.name, [ 
                    self.name + " started for " + ref_time,
                    "file obstore_" + ref_time + ".um ready",
                    "file bgerr" + ref_time + ".um ready", 
                    "file lbc_" + lbc_12 + ".um ready",
                    self.name + " finished for " + ref_time
                    ])

        if hour == "06" or hour == "18":

            self.postrequisites = requisites( self.name, [
                    self.name + " started for " + ref_time,
                    "file obstore_" + ref_time + ".um ready",
                    "file bgerr" + ref_time + ".um ready",
                    "file lbc_" + lbc_06 + ".um ready",
                    self.name + " finished for " + ref_time
                    ])
            
#----------------------------------------------------------------------
class oper_to_topnet( runahead_task_base ):
    "connect separate operational system to a topnet task"

    """use instead of downloader"""

    name = "oper_to_topnet"
    valid_hours = [ 6, 18 ]

    def __init__( self, ref_time, initial_state = "waiting" ):
        
        runahead_task_base.__init__( self, ref_time, initial_state )
        # note: base class init may adjust ref_time!

        # no prerequisites: this is The Initial Task
        self.prerequisites = requisites( self.name, [])

        self.estimated_run_time = 1

        self.postrequisites = requisites( self.name, [
                self.name + " started for " + ref_time,
                "file tn_" + ref_time + ".nc ready",
                self.name + " finished for " + ref_time
                ])

#----------------------------------------------------------------------
class nzlam( task_base ):

    name = "nzlam"
    valid_hours = [ 0, 6, 12, 18 ]

    def __init__( self, ref_time, initial_state = "waiting" ):

        task_base.__init__( self, ref_time, initial_state )

        hour = ref_time[8:10]

        if hour == "00" or hour == "12":
            self.estimated_run_time = 50
        elif hour == "06" or hour == "18":
            self.estimated_run_time = 120

        lbc_06 = reference_time.decrement( ref_time, 6 )
        lbc_12 = reference_time.decrement( ref_time, 12 )

        if hour == "00" or hour == "12":
            self.prerequisites = requisites( self.name, [ 
                "file obstore_" + ref_time + ".um ready",
                "file bgerr" + ref_time + ".um ready",
                "file lbc_" + lbc_12 + ".um ready" 
                ])

            self.postrequisites = requisites( self.name, [ 
                self.name + " started for " + ref_time,
                "file sls_" + ref_time + ".um ready",   
                self.name + " finished for " + ref_time
                ])
 
        elif hour == "06" or hour == "18":
            self.prerequisites = requisites( self.name, [ 
                "file obstore_" + ref_time + ".um ready",
                "file bgerr" + ref_time + ".um ready",
                "file lbc_" + lbc_06 + ".um ready" 
                ])

            self.postrequisites = requisites( self.name, [ 
                self.name + " started for " + ref_time,
                "file tn_" + ref_time + ".um ready",
                "file sls_" + ref_time + ".um ready",   
                "file met_" + ref_time + ".um ready",
                self.name + " finished for " + ref_time
                ])

#----------------------------------------------------------------------
class nzlam_post( task_base ):

    name = "nzlam_post"
    valid_hours = [ 0, 6, 12, 18 ]

    def __init__( self, ref_time, initial_state = "waiting" ):

        task_base.__init__( self, ref_time, initial_state )

        hour = ref_time[8:10]

        if hour == "00" or hour == "12":
            self.estimated_run_time = 10 
        elif hour == "06" or hour == "18":
            self.estimated_run_time = 40

        if hour == "00" or hour == "12":
            
            self.prerequisites = requisites( self.name, [ 
                "file sls_" + ref_time + ".um ready",   
                ])

            self.postrequisites = requisites( self.name, [
                self.name + " started for " + ref_time,
                "file sls_" + ref_time + ".nc ready",   
                self.name + " finished for " + ref_time
                ])

        elif hour == "06" or hour == "18":

            self.prerequisites = requisites( self.name, [ 
                "file tn_" + ref_time + ".um ready",
                "file sls_" + ref_time + ".um ready",   
                "file met_" + ref_time + ".um ready" 
                ])

            self.postrequisites = requisites( self.name, [ 
                self.name + " started for " + ref_time,
                "file tn_" + ref_time + ".nc ready",
                "file sls_" + ref_time + ".nc ready",   
                "file met_" + ref_time + ".nc ready",
                self.name + " finished for " + ref_time
                ])

#----------------------------------------------------------------------
class globalprep( task_base ):
    name = "globalprep"
    valid_hours = [ 0 ]

    def __init__( self, ref_time, initial_state = "waiting" ):

        task_base.__init__( self, ref_time, initial_state )

        self.estimated_run_time = 5

        hour = ref_time[8:10]

        self.prerequisites = requisites( self.name, [ 
                "file 10mwind_" + ref_time + ".um ready",
                "file seaice_" + ref_time + ".um ready" ])

        self.postrequisites = requisites( self.name, [
                self.name + " started for " + ref_time,
                "file 10mwind_" + ref_time + ".nc ready",
                "file seaice_" + ref_time + ".nc ready",
                self.name + " finished for " + ref_time
                ])
       
#----------------------------------------------------------------------
class globalwave( task_base ):

    name = "globalwave"
    valid_hours = [ 0 ]

    def __init__( self, ref_time, initial_state = "waiting" ):

        task_base.__init__( self, ref_time, initial_state )

        self.estimated_run_time = 120 

        self.prerequisites = requisites( self.name, [ 
                "file 10mwind_" + ref_time + ".nc ready",
                "file seaice_" + ref_time + ".nc ready" ])

        self.postrequisites = requisites( self.name, [
                self.name + " started for " + ref_time,
                "file globalwave_" + ref_time + ".nc ready",
                self.name + " finished for " + ref_time
                ])
        
#----------------------------------------------------------------------
class nzwave( task_base ):
    
    name = "nzwave"
    valid_hours = [ 0, 6, 12, 18 ]

    def __init__( self, ref_time, initial_state = "waiting" ):

        task_base.__init__( self, ref_time, initial_state )

        hour = ref_time[8:10]

        if hour == "06" or hour == "18":
            self.estimated_run_time = 120
        else:
            self.estimated_run_time = 30

        self.prerequisites = requisites( self.name, [ 
                 "file sls_" + ref_time + ".nc ready" ])

        self.postrequisites = requisites( self.name, [
                self.name + " started for " + ref_time,
                "file nzwave_" + ref_time + ".nc ready",
                self.name + " finished for " + ref_time
                ])
        
#----------------------------------------------------------------------
class ricom( task_base ):
    
    name = "ricom"
    valid_hours = [ 6, 18 ]

    def __init__( self, ref_time, initial_state = "waiting" ):

        task_base.__init__( self, ref_time, initial_state )

        self.estimated_run_time = 30 

        self.prerequisites = requisites( self.name, [ 
                 "file sls_" + ref_time + ".nc ready" ])

        self.postrequisites = requisites( self.name, [
                self.name + " started for " + ref_time,
                "file ricom_" + ref_time + ".nc ready",
                self.name + " finished for " + ref_time
                ])
        
#----------------------------------------------------------------------
class mos( task_base ):
    
    name = "mos"
    valid_hours = [ 0, 6, 12, 18 ]

    def __init__( self, ref_time, initial_state = "waiting" ):

        task_base.__init__( self, ref_time, initial_state )

        self.estimated_run_time = 0.1

        hour = ref_time[8:10]

        if hour == "06" or hour == "18":
            self.prerequisites = requisites( self.name, [ 
                "file met_" + ref_time + ".nc ready"
                ])
        else:
            self.prerequisites = requisites( self.name, [])

        self.postrequisites = requisites( self.name, [
                self.name + " started for " + ref_time,
                "file mos_" + ref_time + ".nc ready",
                self.name + " finished for " + ref_time
                ])

#----------------------------------------------------------------------
class nztide( runahead_task_base ):
    
    name = "nztide"
    valid_hours = [ 6, 18 ]

    def __init__( self, ref_time, initial_state = "waiting" ):

        runahead_task_base.__init__( self, ref_time, initial_state )

        self.estimated_run_time = 1

        self.prerequisites = requisites( self.name, [])

        self.postrequisites = requisites( self.name, [
                self.name + " started for " + ref_time,
                "file nztide_" + ref_time + ".nc ready",
                self.name + " finished for " + ref_time
                ])

#----------------------------------------------------------------------
class topnet( task_base ):
    "streamflow data extraction and topnet" 

    """If no other tasks dependend on the streamflow data then it's
    easiest to make streamflow part of the topnet task, because of
    the unusual runahead behavior of topnet"""
 
    name = "topnet"
    valid_hours = range( 0,24 )

    # assume catchup mode and detect if we've caught up
    catchup_mode = True
    # (SHOULD THIS BE BASED ON TOPNET OR DOWNLOADER?)

    def __init__( self, ref_time, initial_state = "waiting" ):

        task_base.__init__( self, ref_time, initial_state )

        self.estimated_run_time = 0.01

        self.postrequisites = requisites( self.name, [ 
                self.name + " started for " + ref_time,
                "file topnet_" + ref_time + ".nc ready",
                self.name + " finished for " + ref_time
                ])

        if topnet.catchup_mode:
            nzlam_cutoff = reference_time.decrement( self.ref_time, 11 )
        else:
            nzlam_cutoff = reference_time.decrement( self.ref_time, 23 )
 
        self.prerequisites = fuzzy_requisites( self.name, [ 
                "file tn_" + nzlam_cutoff + ".nc ready" ])


    def run_external_dummy( self, dummy_clock_rate ):
        # RUN THE EXTERNAL TASK AS A SEPARATE PROCESS
        # TO DO: the subprocess module might be better than os.system?

        # for topnet, supply name of most recent nzlam file from the
        # sharpened fuzzy prerequisite

        prereqs = self.prerequisites.get_list()
        prereq = prereqs[0]
        m = re.compile( "^file (.*) ready$" ).match( prereq )
        [ file ] = m.groups()

        self.log.info( "launching external dummy for " + self.ref_time + " (off " + file + ")" )
        os.system( "./task_dummy.py " + self.name + " " + self.ref_time + " " + str(dummy_clock_rate) + " &" )
        self.state = "running"


    def incoming( self, priority, message ):

        # pass on to the base class message handling function
        task_base.incoming( self, priority, message)

        # but intercept catchup mode messages
        if not topnet.catchup_mode and message == "CATCHUP for " + self.ref_time:
            topnet.catchup_mode = True
            # WARNING: SHOULDN'T GO FROM UPTODATE TO CATCHUP?
            self.log.warning( "beginning CATCHUP operation" )

        elif topnet.catchup_mode and message == "UPTODATE for " + self.ref_time:
            topnet.catchup_mode = False
            self.log.info( "beginning UPTODATE operation" )

#----------------------------------------------------------------------
class nwpglobal( task_base ):

    name = "nwpglobal"
    valid_hours = [ 0 ]

    def __init__( self, ref_time, initial_state = "waiting" ):

        task_base.__init__( self, ref_time, initial_state )

        self.estimated_run_time = 10

        self.prerequisites = requisites( self.name, [ 
                 "file 10mwind_" + ref_time + ".um ready" ])

        self.postrequisites = requisites( self.name, [
                self.name + " started for " + ref_time,
                "file 10mwind_" + ref_time + ".nc ready",
                self.name + " finished for " + ref_time
                ])
