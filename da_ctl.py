import time
import sys
import logging
import importlib
import schedule
import setproctitle
from timeloop import Timeloop
from datetime import timedelta
from lxml import etree as cfg_tree
from lxml import etree as out_tree
from lib.common import create_msg, pub_mqtt_msg
from lib.common import C_FunctBase, C_Input, C_Output, C_Counter, C_PreFetch
from lib.common import C_MqttBroker, C_DataBase, C_Plc_Eth, C_MB_TCP, C_StompBroker, C_Server, C_MsgQueue
setproctitle.setproctitle('da_control')  # Sets the display name in the OS
out_tree.register_namespace('p', 'http://www.mesa.org/xml/B2MML')
ns = 'http://www.mesa.org/xml/B2MML'

config_path = 'gen_config'
config_file = 'cfg_write_udp.xml'

#  global functions
functions = {}
funct_dict = {}
poll_timers = {}  # Create a dict of poll timers
sched_timers = {}  # Create a dict of schedule timers
connections = {}  # Dict of connections


def load_config(ct):
    try:
        # global lcd_enable
        # lcd_enable = ct.find('lcd_enable').text
        mqb = ct.find('mqtt_broker')
        # global mqtt
        mqtt = C_MqttBroker(mqb.find('hostname').text,
                            mqb.find('username').text,
                            mqb.find('password').text,
                            mqb.find('port').text,
                            mqb.find('tls').text,
                            mqb.find('qos').text,
                            mqb.find('retain').text,)

        functs = ct.find('functions')
        if functs is not None:
            for function in functs.iterfind('.//function'):
                ip_dict = {}
                op_dict = {}
                ct_dict = {}
                cd = None
                f_name = function.find('f_name').text
                f_type = function.find('f_type').text

                inputs = function.find('inputs')
                if inputs is not None:
                    for inp in inputs.iterfind('.//input'):
                        ip = C_Input(inp.find('ip_tag').text,
                                     inp.find('ip_link').text,
                                     inp.find('ip_data_type').text)
                        ip_dict[ip.ip_tag] = ip

                outputs = function.find('outputs')
                if outputs is not None:
                    for otp in outputs.iterfind('.//output'):
                        op_tag = otp.find('op_tag')
                        op_link = otp.find('op_link')
                        if otp.find('op_fail_dly') is not None: # Check if there is a fail delay
                            ofd = otp.find('op_fail_dly').text # Is so get the value
                        else:
                            ofd = 0

                        op = C_Output(op_tag.text,
                                     op_tag.get('mode'),
                                     op_link.text,
                                     op_link.get('comp'),
                                     op_link.get('cval'),
                                     otp.find('op_index').text,
                                     otp.find('op_data_type').text,
                                     ofd)
                        op_dict[op.op_tag] = op

                counters = function.find('counters')
                if counters is not None:
                    for counter in counters.iterfind('.//counter'):
                        ct = C_Counter(counter.find('ct_tag').text,
                                      counter.find('ct_link').text,
                                      counter.find('ct_index').text,
                                      counter.find('ct_data_type').text,
                                      counter.find('ct_fail_dly').text)
                        ct_dict[ct.ct_tag] = ct

                pre_fetch = function.find('pre_fetch')
                if pre_fetch is not None:
                    pf = C_PreFetch(pre_fetch.find('pf_type').text,
                                   pre_fetch.find('pf_tags').text,
                                   pre_fetch.find('pf_val').text)
                else:
                    pf = None

                at = {} # Declare an aux tag dict
                aux_tags = function.find('aux_tags')
                if aux_tags is not None:
                    for aux_tag in aux_tags.iterfind('.//aux_tag'):
                        name = aux_tag.get('name')
                        val = aux_tag.text
                        at[name] = val

                com_dat = function.find('f_com_dat')
                if com_dat is not None:
                    if com_dat.get('type') == 'database':  # If the communication type is a database
                        sql_db = com_dat.find('sql_database')
                        poll_time = com_dat.get('poll_time')
                        if poll_time is None:
                            poll_time = ''
                        cd = C_DataBase(sql_db.find('host_ip').text,
                                         sql_db.find('name').text,
                                         sql_db.find('user_name').text,
                                        sql_db.find('password').text,
                                        poll_time)
                    elif com_dat.get('type') == 'plc_eth':  # If the communication type is an Ethernet PLC
                        plc = com_dat.find('plc')
                        cd = C_Plc_Eth(plc.find('host_ip').text,
                                       plc.find('rack').text,
                                       plc.find('slot').text,
                                       com_dat.get('poll_time'))

                    elif com_dat.get('type') == 'modbus_tcp':  # If the communication type is a Modbus TCP/IP device
                        mbtcp = com_dat.find('modbus_tcp')
                        cd = C_MB_TCP(mbtcp.find('host_ip').text,
                                       mbtcp.find('port').text,
                                       com_dat.get('poll_time'))

                    elif com_dat.get('type') == 'activemq_stomp':  # If the communication type is an Active MQ host
                        stomp = com_dat.find('activemq_stomp')
                        cd = C_StompBroker(stomp.find('host_ip').text,
                                           stomp.find('username').text,
                                           stomp.find('password').text,
                                           stomp.find('port').text,
                                           com_dat.get('poll_time'))

                    elif com_dat.get('type') == 'server':  # If the communication type is a Server
                        serv = com_dat.find('server')
                        cd = C_Server(serv.find('host_ip').text,
                                           serv.find('username').text,
                                           serv.find('password').text,
                                           serv.find('port').text,
                                           com_dat.get('poll_time'))

                    elif com_dat.get('type') == 'mqtt':  # If the communication type is a mqtt queue
                        mq = com_dat.find('mq')
                        cd = C_MsgQueue(mq.find('hostname').text,
                                          mq.find('username').text,
                                          mq.find('password').text,
                                          mq.find('port').text,
                                          mq.find('tls').text,
                                          com_dat.get('poll_time'))

                    elif com_dat.get('type') == 'mqttbroker':  # If the communication type is a mqtt queue
                        mq = com_dat.find('mq')
                        cd = C_MqttBroker(mq.find('hostname').text,
                                          mq.find('username').text,
                                          mq.find('password').text,
                                          mq.find('port').text,
                                          mq.find('tls').text,
                                          mq.find('qos').text,
                                          mq.find('retain').text,
                                          com_dat.get('poll_time'))

                funct = C_FunctBase(f_name, f_type, ip_dict, op_dict, ct_dict, pf, mqtt, cd, at)  # Create a FuncBase class object
                logger.info('Added={}'.format(f_name))
                funct_dict[f_name] = funct  # Add the function object to the main function dict

        logger.info('Config Complete')
    except Exception as e:
        logger.warning('WARNING-LoadConfigError={}'.format(e))


def cnf_logger():
    # Open the config file
    ct = cfg_tree.parse('./'+ config_path + '/' + config_file)  # parse the config file into a tree
    log_level = None
    # Get the log level
    for ll in ct.iterfind('.//ll'):
        log_level = int(ll.find('log_level').text)

    # Create and configure logger
    if log_level == 0:  # Logs WARNINGS to log file
        logging.basicConfig(format='%(asctime)s %(message)s',
                            level=logging.WARNING)

    elif log_level == 1:  # Logs local code INFO and snap7 WARNINGS to terminal window
        logging.basicConfig(format='%(asctime)s %(message)s', level=logging.WARNING)

    elif log_level == 2:  # Logs local code DEBUG and snap7 WARNINGS to terminal window
        logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)

    elif log_level == 3:  # Logs local code DEBUG and snap7 WARNINGS to terminal window
        logging.basicConfig(format='%(asctime)s %(message)s', level=logging.DEBUG)

    global logger
    logger = logging.getLogger()
    logger.warning('System Startup, Log Level={}'.format(log_level))
    return ct, logger


def process_funct(fb):
    try:
        logger.info('Process={}'.format(fb.name))
        if hasattr(fb, 'com_dat'):
            poll_times = fb.com_dat.pt  # Get the poll time
            if poll_times is not None:  # If the poll times is not none
                poll_list = poll_times.split(',')  # Split the poll times into a list
                for poll_time in poll_list:  # Iterate through the list
                    if poll_time == '':  # If the poll time is a blank string
                        call_funct(fb)  # Call the function block
                    elif poll_time.isnumeric():  # And if the poll time is a number
                        if fb.name not in poll_timers:  # If the timer is not already in the dict of poll timers
                            tl = Timeloop()  # Create a new timeloop object

                            @tl.job(interval=timedelta(seconds=int(poll_time)))  # Configure the timer
                            def poll_coms():  # Create a function to poll the function
                                call_funct(fb)  # Poll the function

                            tl.start()  # Start the timer
                            poll_timers[fb.name] = tl  # Add the timer to the timers dict
                            logger.info('AddedPollTimerFor={}'.format(fb.name))
                            call_funct(fb)  # Call the function block
                    elif poll_time[0] == '@':  # If the polltime is a scheduled time
                        pt = poll_time[1:9]   # Trim the '@' charecter off the string
                        schedule.every().day.at(pt).do(call_funct, fb)  # Schedule the job
                        logger.info('AddedSchedTimerFor={}'.format(fb.name))
                        call_funct(fb)  # Call the function block

            else:
                call_funct(fb)  # Call the function block
        else:
            call_funct(fb)  # Call the function block

    except Exception as e:
        logger.warning('ProcFunctError={}, Equip={}'.format(e, fb.type))


def call_funct(fb):
    try:
        if fb.name not in functions:
            module = importlib.import_module('lib.' + fb.type, )  # Import the function block module and create an instance
            my_class = getattr(module, fb.type)
            # print('created a ', type(my_class), 'class object')
            functions[fb.name] = my_class(fb, logger)

        rslt = functions[fb.name].process()  # Call the function block
        logger.info('Returned from={}, Result={}'.format(fb.name, rslt))
        if rslt:  # If the function block returns a True status or the publish bit is set

            pub_mqtt_msg(fb, create_msg(fb, logger), logger)  # Publish the function's data

    except Exception as e:
        logger.warning('CallFunctError={}, Equip={}'.format(e, fb.type))


def sys_init():
    try:
        ct, logger = cnf_logger()  # Configure the logger and open the config file
        load_config(ct)  # Load the config file and create the function block dict
        for fb in funct_dict:  # Loop through the function blocks
            print('Process', funct_dict[fb].name)
            process_funct(funct_dict[fb])  # Call the 'process function for the block'
            time.sleep(0.2)
    except Exception as e:
        print('SysInitError={}'.format(e))


if __name__ == '__main__':
    sys_init()  # Call the system initialisation routine

    while True:
        try:
            schedule.run_pending()
            time.sleep(1)  # wait one second

        except KeyboardInterrupt:
            for tl in poll_timers:  # Iterate thorough the poll timers
                poll_timers[tl].stop()  # Stop the poll timer
            for fb in funct_dict:  # Iterate through the functions
                if hasattr(fb, 'com_dat'):  # If the function has a 'com_dat' object
                    if hasattr(fb.com_dat.cn, 'close'):  # If the 'com_dat' object has a 'close' function
                        fb.com_dat.cn.close()  # Close the function

            sys.exit()

