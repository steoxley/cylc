#!/usr/bin/env python

# NOT YET IMPLEMENTED OR DOCUMENTED FROM bin/_taskgen:
#   - conditional prerequisites
#   - short name
#   - task inheritance
#   - FAMILY
#   - asynch stuff, output_patterns
#   - no longer interpolate ctime in env vars or scripting 
#     (not needed since cylcutil?) 
#
#         __________________________
#         |____C_O_P_Y_R_I_G_H_T___|
#         |                        |
#         |  (c) NIWA, 2008-2010   |
#         | Contact: Hilary Oliver |
#         |  h.oliver@niwa.co.nz   |
#         |    +64-4-386 0461      |
#         |________________________|

import os, sys, re, string
from OrderedDict import OrderedDict

class Error( Exception ):
    """base class for exceptions in this module."""
    pass

class DefinitionError( Error ):
    """
    Exception raise for errors in taskdef initialization.
    """
    def __init__( self, msg ):
        self.msg = msg
    def __str__( self ):
        return repr( self.msg )

class taskdef:
    allowed_types = [ 'free', 'tied' ]
    allowed_modifiers = [ 'sequential', 'oneoff', 'dummy', 'contact', 'catchup_contact' ]

    task_init_def_args = 'c_time, initial_state, startup = False'
    #task_inherit_super_args = 'c_time, initial_state, startup'
    task_init_args = 'initial_state'

    task_class_preamble = '''
#!/usr/bin/env python

#         __________________________
#         |____C_O_P_Y_R_I_G_H_T___|
#         |                        |
#         |  (c) NIWA, 2008-2010   |
#         | Contact: Hilary Oliver |
#         |  h.oliver@niwa.co.nz   |
#         |    +64-4-386 0461      |
#         |________________________|

# THIS FILE WAS AUTO-GENERATED BY CYLC

from daemon import daemon
from asynchronous import asynchronous
from cycling_daemon import cycling_daemon
from tied import tied
from free import free
from family import family
from mod_oneoff import oneoff
from mod_sequential import sequential
from mod_contact import contact
from mod_catchup_contact import catchup_contact
from prerequisites_fuzzy import fuzzy_prerequisites
from prerequisites import prerequisites
from outputs import outputs
from time import sleep
from task_output_logs import logfiles
import cycle_time
import task_state
from OrderedDict import OrderedDict
from collections import deque

'''

    def __init__( self, name, short_name=None ):
        self.name = name
        if not short_name:
            self.shortname = name 

        self.type = 'free'

        self.modifiers = []

        self.owner = None
        self.host = None

        self.intercycle = False
        self.hours = []
        self.logfiles = []
        self.description = ['Task description has not been completed' ]

        self.members = []
        self.member_of = None
        self.follow_on_task = None

        # use dicts quantities that may be conditional on cycle hour
        # keyed on condition
        # OrderedDict keeps 'any' conditional at the top if entered
        # first
        self.n_restart_outputs = OrderedDict()            # int
        self.contact_offset = OrderedDict()               # float hours
        self.prerequisites = OrderedDict()                # list of messages
        self.suicide_prerequisites = OrderedDict()        #  "
        self.coldstart_prerequisites = OrderedDict()      #  "
        self.conditional_prerequisites = OrderedDict()    #  "
        self.outputs = OrderedDict()                      #  "

        self.commands = OrderedDict()                     # list of commands
        self.commands['any'] = ['cylc-wrapper true']      # default: dummied out

        self.scripting = OrderedDict()                    # list of lines
        self.environment = OrderedDict()                  # OrderedDict() of var = value
        self.directives = OrderedDict()                   # OrderedDict() of var = value

        self.indent = ''
        self.indent_unit = '  '

    def set_type( self, t ):
        # free
        # tied( n_restart_outputs )
        m = re.match( '(tied)\((\d+)\)', t )
        if m:
            type = m.groups()[0]
            self.n_restart_outputs['any'] = int( m.groups()[1] )
        else:
            type = t
        if type not in self.__class__.allowed_types:
            raise DefinitionError( "Illegal task type: " + type )
        self.type = type

    def set_modifiers( self, mods = [] ):
        # dummy, sequential, oneoff
        # contact(offset)
        # catchup_contact(offset)
        # TO DO: DUMMY MODIFIER NO LONGER NECESSARY
        for mod in mods:
            print mod
            m = re.match( '(contact.*)\((\d+)\)', mod )
            if m:
                self.contact_offset['any'] = int( m.groups()[1] )
                modifier = m.groups()[0]
            else:
                modifier = mod

            if modifier not in self.__class__.allowed_modifiers:
                raise DefinitionError( "Illegal task type modifier: " + modifier )

            self.modifiers.append( modifier )


    def add_default_output( self, hour='any' ):
        if hour not in self.outputs:
            self.outputs[hour] = []
        n = len( self.outputs[hour] ) + 1
        msg = "\"Task " + self.name + " output " + str(n) + " ready for \" + self.c_time"
        if msg in self.outputs[hour]:
            raise DefinitionError( "Output already defined: " + msg )
        self.outputs[hour].append( msg )

    def add_default_prerequisite( self, task, hour='any', n=1 ):
        # trigger off task's default output 1
        if hour not in self.prerequisites:
            self.prerequisites[hour] = []
        msg = "\"Task " + task + " output " + str(n) + " ready for \" + self.c_time"
        if msg in self.prerequisites[hour]:
            raise DefinitionError( "Output already defined: " + msg )
        self.prerequisites[hour].append( msg )

    def dump( self, FILE=None ):
        if not FILE:
            FILE=sys.stdout

        indent = '   '
        print >> FILE, '%TASK'
        print >> FILE, indent, self.name

        print >> FILE, '%DESCRIPTION'
        for line in self.description:
            print >> FILE, indent, line

        print >> FILE, '%HOURS'
        hrs = str( self.hours[0] )
        for hour in self.hours[1:]:
            hrs = hrs + ', ' + str(hour)
        print >> FILE, indent, hrs

        print >> FILE, '%TYPE'
        types = [ self.type ] + self.modifiers
        print >> FILE, indent, ', '.join( types )

        if self.owner:
            print >> FILE, '%OWNER'
            print >> FILE, indent, self.owner

        if self.host:
            print >> FILE, '%REMOTE_HOST'
            print >> FILE, indent, self.host

        self.dump_conditional_list( FILE, self.commands,      'COMMAND'       )
        self.dump_conditional_list( FILE, self.prerequisites, 'PREREQUISITES', quote=True )
        self.dump_conditional_list( FILE, self.outputs,       'OUTPUTS', quote=True       )
        self.dump_conditional_dict( FILE, self.environment,   'ENVIRONMENT'   )
        self.dump_conditional_list( FILE, self.scripting,     'SCRIPTING'     )
        self.dump_conditional_dict( FILE, self.directives,    'DIRECTIVES'    )

    def dump_conditional_list( self, FILE, foo, name, quote=False ):
        # print out foo[condition] = []
        indent = '   '
        print >> FILE, '%' + name
        for condition in foo:
            values = foo[condition]
            if condition == 'any':
                for value in values:
                    if quote:
                        value = '"' + value + '"'
                    print >> FILE, indent, value
            else:
                print >> FILE, indent, 'if HOUR in ' + condition + ':'
                if len( values ) == 0:
                    print >> FILE, indent, indent, "# (none)"
                else:
                    for value in values:
                        if quote:
                            value = '"' + value + '"'
                        print >> FILE, indent, indent, value

    def dump_conditional_dict( self, FILE, foo, name ):
        # print out foo[condition][var] = value
        indent = '   '
        print >> FILE, '%' + name
        for condition in foo:
            vars = foo[condition].keys()
            if condition == 'any':
                for var in vars:
                    print >> FILE, indent, indent, foo[condition][var]
            else:
                print >> FILE, indent, 'if HOUR in ' + condition + ':'
                if len( vars ) == 0:
                    print >> FILE, indent, indent, "# (none)"
                else:
                    for var in vars:
                        print >> FILE, indent, indent, foo[condition][var]

    def check_name( self, name ):
        m = re.match( '^(\w+),\s*(\w+)$', name )
        if m:
            name, shortname = m.groups()
            if re.search( '[^\w]', shortname ):
                raise DefinitionError( 'Task names may contain only a-z,A-Z,0-9,_' )

        if re.search( '[^\w]', name ):
            raise DefinitionError( 'Task names may contain only a-z,A-Z,0-9,_' )
 
    def check_type( self, type ): 
        if type not in self.__class__.allowed_types:
            raise DefinitionError( 'Illegal task type: ' + type )

    def check_modifier( self, modifier ):
        if modifier not in self.__class__.allowed_modifiers:
            raise DefinitionError( 'Illegal task type modifier: ' + modifier )

    def check_set_hours( self, hours ):
        for hr in hours:
            hour = int( hr )
            if hour < 0 or hour > 23:
                raise DefinitionError( 'Hour must be 0<hour<23' )
            self.hours.append( hour )

    def check_consistency( self ):
        if len( self.hours ) == 0:
            raise DefinitionError( 'no hours specified' )

        if 'contact' in self.modifiers:
            if len( self.contact_offset.keys() ) == 0:
                raise DefinitionError( 'contact tasks must specify a time offset' )

        if self.type == 'tied' and self.n_restart_outputs == 0:
            raise DefinitionError( 'tied tasks must specify number of restart outputs' )

        if 'oneoff' not in self.modifiers and self.intercycle:
            if not self.follow_on_task:
                raise DefinitionError( 'oneoff intercycle tasks must specify a follow-on task' )

        if self.member_of and len( self.members ) > 0:
            raise DefinitionError( 'nested task families are not allowed' )

    def append_to_condition_list( self, parameter, condition, value ):
        if condition in parameter.keys():
            parameter[condition].append( value )
        else:
            parameter[condition] = [ value ]

    def add_to_condition_dict( self, parameter, condition, var, value ):
        if condition in parameter.keys():
            parameter[condition][var] = value
        else:
            parameter[condition] = {}
            parameter[condition][var] = value

    def indent_more( self ):
        self.indent += self.indent_unit

    def indent_less( self ):
        self.indent = re.sub( self.indent_unit, '',  self.indent, 1 )

    def write_task_class( self, dir ):
        self.classfile = '__' + self.name + '.py'
        outfile = os.path.join( dir, self.classfile )

        # TO DO: EXCEPTION HANDLING FOR DIR NOT FOUND ...
        OUT = open( outfile, 'w' )

        OUT.write( self.__class__.task_class_preamble )

        # task class multiple inheritance
        # this assumes the order of modifiers does not matter
        derived_from = self.type
        if len( self.modifiers ) >= 1:
            derived_from = ','.join( self.modifiers ) + ', ' + derived_from

        OUT.write( 'class ' + self.name + '(' + derived_from + '):\n' )
        self.indent_more()

        OUT.write( self.indent + '# AUTO-GENERATED BY CYLC\n\n' )  
 
        OUT.write( self.indent + 'name = \'' + self.name + '\'\n' )
        OUT.write( self.indent + 'short_name = \'' + self.name + '\'\n' )

        OUT.write( self.indent + 'instance_count = 0\n\n' )

        OUT.write( self.indent + 'description = []\n' )
        for line in self.description:
            OUT.write( self.indent + 'description.append("' + self.escape_quotes(line) + '")\n' )
            OUT.write( '\n' )
 
        if self.owner:
            OUT.write( self.indent + 'owner = \'' + self.owner + '\'\n' )
        else:
            OUT.write( self.indent + 'owner = None\n' )

        if self.host:
            OUT.write( self.indent + 'remote_host = \'' + self.host + '\'\n' )
        else:
            OUT.write( self.indent + 'remote_host = None\n' )

        # can this be moved into task base class?
        OUT.write( self.indent + 'job_submit_method = None\n' )

        OUT.write( self.indent + 'valid_hours = [' )
        hrs = str( self.hours[0] )
        for hour in self.hours[1:]:
            hrs = hrs + ', ' + str(hour)
        OUT.write( hrs + ']\n\n' )

        if self.intercycle:
            OUT.write( self.indent + 'intercycle = ' + str(self.intercycle) + '\n\n' )

        if self.follow_on_task:
            OUT.write( self.indent + 'follow_on = "' + self.follow_on_task + '"\n\n' )

        # class init function
        OUT.write( self.indent + 'def __init__( self, ' + self.__class__.task_init_def_args + ' ):\n\n' )

        self.indent_more()

        OUT.write( self.indent + '# adjust cycle time to next valid for this task\n' )
        OUT.write( self.indent + 'self.c_time = self.nearest_c_time( c_time )\n' )
        OUT.write( self.indent + 'self.tag = self.c_time\n' )
        OUT.write( self.indent + 'self.id = self.name + \'%\' + self.c_time\n' )
        #### FIXME ASYNC
        OUT.write( self.indent + 'hour = self.c_time[8:10]\n\n' )

        # external task
        OUT.write( self.indent + 'self.external_tasks = deque()\n' )

        for condition in self.commands:
            for command in self.commands[ condition ]:
                if condition == 'any':
                    OUT.write( self.indent + 'self.external_tasks.append( \'' + command + '\')\n' )
                else:
                    hours = re.split( ',\s*', condition )
                    for hour in hours:
                        OUT.write( self.indent + 'if int( hour ) == ' + hour + ':\n' )
                        self.indent_more()
                        OUT.write( self.indent + 'self.external_tasks.append( \'' + command + '\')\n' )
                        self.indent_less()
 
        if 'contact' in self.modifiers:
            for condition in self.contact_offset:
                offset = self.contact_offset[ condition ]
                if condition == 'any':
                    OUT.write( self.indent + 'self.real_time_delay = ' +  str( offset ) + '\n' )
                else:
                    hours = re.split( ',\s*', condition )
                    for hour in hours:
                        OUT.write( self.indent + 'if int( hour ) == ' + hour + ':\n' )
                        self.indent_more()
                        OUT.write( self.indent + 'self.real_time_delay = ' + str( offset ) + '\n' )
                        self.indent_less()
 
            OUT.write( '\n' )

        self.write_requisites( OUT, 'prerequisites', 'prerequisites', self.prerequisites )
        self.write_requisites( OUT, 'suicide_prerequisites', 'prerequisites', self.suicide_prerequisites )

        OUT.write( self.indent + 'self.logfiles = logfiles()\n' )
        for lfile in self.logfiles:
            OUT.write( self.indent + 'self.logfiles.add_path("' + lfile + '")\n' )

        self.write_requisites( OUT, 'outputs', 'outputs', self.outputs )

        if self.type == 'tied':
            for condition in self.n_restart_outputs.keys():
                n = self.n_restart_outputs[ condition ]
                if condition == 'any':
                    OUT.write( self.indent + 'self.register_restart_requisites(' + str(n) +')\n' )
                else:
                    hours = re.split( ', *', condition )
                    for hour in hours:
                        OUT.write( self.indent + 'if int( hour ) == ' + hour + ':\n' )
                        self.indent_more()
                        OUT.write( self.indent + 'self.register_restart_requisites(' + str( n ) + ')\n' )
                        self.indent_less()
 
        OUT.write( self.indent + 'self.outputs.register()\n\n' )

        # override the above with any coldstart prerequisites
        self.write_requisites( OUT, 'coldstart_prerequisites', 'prerequisites', self.coldstart_prerequisites )

        OUT.write( '\n' + self.indent + 'self.env_vars = OrderedDict()\n' )
        OUT.write( self.indent + "self.env_vars['TASK_NAME'] = self.name\n" )
        OUT.write( self.indent + "self.env_vars['TASK_ID'] = self.id\n" )
        OUT.write( self.indent + "self.env_vars['CYCLE_TIME'] = self.c_time\n" )
       
        for condition in self.environment.keys():
            envdict = self.environment[ condition ]
            for var in envdict.keys():
                val = envdict[ var ]
                if condition == 'any':
                    OUT.write( self.indent + 'self.env_vars[' + var + '] = ' + val + '\n' )
                else:
                    hours = re.split( ', *', condition )
                    for hour in hours:
                        OUT.write( self.indent + 'if int( hour ) == ' + hour + ':\n' )
                        self.indent_more()
                        OUT.write( self.indent + 'self.env_vars[' + var + '] = ' + val + '\n' )
                        self.indent_less()
 
        OUT.write( '\n' + self.indent + 'self.directives = OrderedDict()\n' )
        for condition in self.directives.keys():
            dirdict = self.directives[ condition ]
            for var in dirdict.keys():
                val = dirdict[ var ]
                if condition == 'any':
                    OUT.write( self.indent + 'self.directives[' + var + '] = ' + val + '\n' )
                else:
                    hours = re.split( ', *', condition )
                    for hour in hours:
                        OUT.write( self.indent + 'if int( hour ) == ' + hour + ':\n' )
                        self.indent_more()
                        OUT.write( self.indent + 'self.directives[' + var + '] = ' + val + '\n' )
                        self.indent_less()
 
        OUT.write( '\n' + self.indent + 'self.extra_scripting = []\n' )

        for condition in self.scripting.keys():
            lines = self.scripting[ condition ]
            for line in lines:
                if condition == 'any':
                    OUT.write( self.indent + 'self.extra_scripting.append(' + line + ')\n' )
                else:
                    hours = re.split( ', *', condition )
                    for hour in hours:
                        OUT.write( self.indent + 'if int( hour ) == ' + hour + ':\n' )
                        self.indent_more()
                        OUT.write( self.indent + 'self.extra_scripting.append(' + line + ')\n' )
                        self.indent_less()
 
        OUT.write( '\n' )

        if 'catchup_contact' in self.modifiers:
            OUT.write( self.indent + 'catchup_contact.__init__( self )\n\n' )
 
        OUT.write( self.indent + self.type + '.__init__( self, ' + self.__class__.task_init_args + ' )\n\n' )

        self.indent_less()
        self.indent_less()

        OUT.close()
 
    def write_requisites( self, FILE, req_name, req_type, requisites ):
        FILE.write( self.indent + 'self.' + req_name + ' = ' + req_type + '( self.id )\n' )

        for condition in requisites:
            reqs = requisites[ condition ]
            if condition == 'any':
                for req in reqs:
                    FILE.write( self.indent + 'self.' + req_name + '.add(' +  req + ')\n' )
            else:
                hours = re.split( ',\s*', condition )
                for hour in hours:
                    FILE.write( self.indent + 'if int( hour ) == ' + hour + ':\n' )
                    self.indent_more()
                    FILE.write( self.indent + 'self.' + req_name + '.add(' + req + ')\n' )
                    self.indent_less()

    def escape_quotes( self, strng ):
        return re.sub( '([\\\'"])', r'\\\1', strng )

    def interpolate_conditional_list( self, foo ):
        for condition in foo.keys():
            old_values = foo[ condition ]
            new_values = []
            for value in old_values:
                new_values.append( self.interpolate_cycle_times( value ) )
            foo[condition] = new_values

    def time_trans( self, strng, hours=False ):
        # translate a time of the form:
        #  x sec, y min, z hr
        # into float MINUTES or HOURS,
    
        if not re.search( '^\s*(.*)\s*min\s*$', strng ) and \
            not re.search( '^\s*(.*)\s*sec\s*$', strng ) and \
            not re.search( '^\s*(.*)\s*hr\s*$', strng ):
                print "ERROR: missing time unit on " + strng
                sys.exit(1)
    
        m = re.search( '^\s*(.*)\s*min\s*$', strng )
        if m:
            [ mins ] = m.groups()
            if hours:
                return str( float( mins / 60.0 ) )
            else:
                return str( float(mins) )
    
        m = re.search( '^\s*(.*)\s*sec\s*$', strng )
        if m:
            [ secs ] = m.groups()
            if hours:
                return str( float(secs)/3600.0 )
            else:
                return str( float(secs)/60.0 )
    
        m = re.search( '^\s*(.*)\s*hr\s*$', strng )
        if m:
            [ hrs ] = m.groups()
            if hours:
                #return str( float(hrs) )
                return float(hrs)
            else:
                #return str( float(hrs)*60.0 )
                return float(hrs)*60.0