#################################################################

####        COMMON CODE FUNCTIONS

#################################################################

import time
from gpiozero import CPUTemperature
#import lib.lcd1306 as lcd
from lxml import etree as err_tree
from lxml import etree as out_tree
import paho.mqtt.publish as pub_mqtt
out_tree.register_namespace('p', 'http://www.mesa.org/xml/B2MML')
ns = 'http://www.mesa.org/xml/B2MML'

class C_FunctBase:  # Base class for all functions
    def __init__(self, f_name, f_type, f_inputs, f_outputs, f_counters, f_pre_fetch, f_mq_brkr, f_com_dat=None, aux_tags = None):
        self.name = f_name  # Function Name
        self.type = f_type  # Function type (must exist in the 'lib' directory)
        self.inputs = f_inputs  # List of Input objects
        self.outputs = f_outputs  # List of Output objects
        self.counters = f_counters  # List of Counter objects
        self.pre_fetch = f_pre_fetch  # Pre-fetch function
        self.aux_tags = aux_tags  # Auxiliary tags dict
        self.mq = f_mq_brkr  # ActiveMQ Broker object
        self.pub = False  # Publishing trigger
        self.init = True  # Initialisation trigger
        self.en = False # Function block enabled status
        if f_com_dat is not None:
            self.com_dat = f_com_dat  # Communication object

class C_Input:  #  Input Class
    def __init__(self, ip_tag, ip_link, ip_type):
        self.ip_tag = ip_tag  # Tag Name
        self.ip_link =  ip_link # Input Link
        self.ip_type = ip_type  # Type
        self.ip_val = []  # Value List

class C_Output:  #  Output Class
    def __init__(self, op_tag, op_ud_mode, op_link, op_comp, op_cval, op_index, op_type, op_dly = None):
        self.op_tag = op_tag  # Tag Name
        self.op_ud_mode = op_ud_mode  # Update Mode
        self.op_link = op_link  # Output Link
        if op_comp is not None:
            self.op_comp = [x.strip() for x in op_comp.split(',')]  # List of comparator values
        else:
            self.op_comp = None
        if op_cval is not None:
            self.op_cval = [x.strip() for x in op_cval.split(',')]  # list of replacement values or functions
        else:
            self.op_cval = None
        self.op_index = list(map(int, op_index.split(',')))
        self.op_type = op_type  # Type
        self.op_val = []  # Value List
        if op_dly is not None:
            self.op_dly = float(op_dly)  # Counter stopped dly
        self.op_sts = True  # Counter status
        self.pub = True
        self.op_time = 0.0  #  Last publishing time

class C_Counter:  #  Counter Class
    def __init__(self, ct_tag, ct_link, ct_index, ct_type, ct_dly):
        self.ct_tag = ct_tag
        self.ct_link = ct_link
        self.ct_index = list(map(int, ct_index.split(',')))
        self.ct_type = ct_type
        self.ct_val = []
        self.ct_time = 0.0  #  Last publishing time
        self.ct_dly = float(ct_dly)  #  Counter stopped dly
        self.ct_sts = False  #  Counter status

class C_DataBase:  #  Database Communication Class
    def __init__(self, host_ip, db_name, user_name, password, poll_time = None):
        self.ip = host_ip
        self.db = db_name
        self.un = user_name
        self.pw = password
        self.cn = None  # Connection object
        if poll_time is not None:
            self.pt = poll_time

class C_Plc_Eth:  #  Ethernet PLC Communication Class
    def __init__(self, host_ip, rack, slot, poll_time = None):
        self.ip = host_ip
        self.rk = int(rack)
        self.sl = int(slot)
        self.cn = None  # Connection object
        if poll_time is not None:
            self.pt = poll_time

class C_CAN_Bus:  #  Can-Bus Communication Class
    def __init__(self, channel, bus_type, baudrate, poll_time = None):
        self.ch = str(channel)
        self.bt = str(bus_type)
        self.br = str(baudrate)
        self.cn = None  # Connection object
        if poll_time is not None:
            self.pt = poll_time

class C_MB_TCP:  #  Modbus TCP Communication Class
    def __init__(self, host_ip, port, poll_time = None):
        self.ip = host_ip
        self.po = int(port)
        self.cn = None  # Connection object
        if poll_time is not None:
            self.pt = poll_time

class C_MsgQueue:  #  Old
    def __init__(self, hostname, username, password, port, tls, poll_time = None):
        print('configuring mqtt',hostname, username, password, port, tls, poll_time)
        self.ip = hostname  # IP address or URL of message queue host machine
        self.un = username  # username
        self.pw = password  # password
        self.po = int(port)  # ActiveMQ local = 1883, AmazonMQ cloud = 8883
        self.tl = int(tls)  # ActiveMQ local = 0, AmazonMQ cloud = 1
        if poll_time is not None:
            self.pt = poll_time

class C_MqttBroker:  # MQTT Broker Class
    def __init__(self, host_ip , username, password, port, tls, qos, retain, poll_time = None):
        self.ip = host_ip  # IP address or URL of message queue host machine
        self.un = username  # username
        self.pw = password  # password
        self.po = int(port)  # ActiveMQ local = 1883, AmazonMQ cloud = 8883
        self.tl = int(tls)  # ActiveMQ local = 0, AmazonMQ cloud = 1
        self.qo = int(qos)  # Quality of service
        self.rt = bool(retain)  # Retain messages
        if poll_time is not None:
            self.pt = poll_time

class C_StompBroker:  # Stomp Broker Class
    def __init__(self, host_ip, username, password, port, poll_time = None):
        self.ip = host_ip  # IP address or URL of message queue host machine
        self.un = username  # username
        self.pw = password  # password
        self.po = int(port)  # Stomp = 61613
        if poll_time is not None:
            self.pt = poll_time

class C_Server:  # Stomp Broker Class
    def __init__(self, host_ip, username, password, port, poll_time = None):
        self.ip = host_ip  # IP address or URL of the server
        self.un = username  # username
        self.pw = password  # password
        self.po = int(port)  # Port Number
        self.cn = None  # Connection object
        if poll_time is not None:
            self.pt = poll_time

class C_PreFetch:  # Pre Fetch Data Class
    def __init__(self, type, tags, val):
        self.tp = type
        self.tg = tags
        self.vl = val

class C_Lcd:
    lcd_data_buf = []
    ud_cnt = 0
    scroll_pos = 0
    def __init__(self, scroll_time):
        self.st = scroll_time

    def update(self):
        self.ud_cnt += 1  # Display update counter
        if self.ud_cnt >= self.st:  # If the counter is greater or equal to the scroll time
            self.ud_disp  # Update the display
            self.ud_cnt = 0  # Reset the counter

    def ud_disp(self):
        cpu_temp = CPUTemperature()

def get_data_itm(itm, idx, lg):
    try:
        length = len(idx)
        if length == 1:
            return itm[idx[0]]
        elif length == 2:
            row = idx[0]
            col = idx[1]
            return itm[row][col]

    except Exception as e:
        lg.warning('WARNING-GetDataError={}'.format(e))


def append_err_msg(msg):
    root = msg.getroot()
    aa = root.find('{' + ns + '}ApplicationArea')

    ua = err_tree.Element('{' + ns + '}UserArea')  # Create a new 'UserArea' element
    ua.tail = '\n'
    ua.text = '\n\t\t'

    error_message = err_tree.SubElement(ua, '{' + ns + '}ErrorMessage')  # Create a tree element
    # Add the required name spaces to the element
    # error_message.set('xmlns:ext', "http://www.mesa.org/xml/B2MML-Extention")
    # error_message.set('xmlns:xsd', "http://www.w3.org/2001/XMLSchema")
    error_message.tail = '\n'
    error_message.text = '\n\t\t\t'

    thrown_from = err_tree.SubElement(error_message, '{' + ns + '}ThrownFrom')  # Create a sub element
    thrown_from.text = 'PTGM1'  # Populate the element text field
    thrown_from.tail = '\n\t\t\t'

    time_stamp = err_tree.SubElement(error_message, '{' + ns + '}TimeStamp')  # Create a sub element
    time_stamp.text = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.localtime())  # Time stamp
    time_stamp.tail = '\n\t\t\t'

    error_type = err_tree.SubElement(error_message, '{' + ns + '}ErrorType')  # Create a sub element
    error_type.text = 'BusinessError'  # Populate the element text field
    error_type.tail = '\n\t\t\t'

    error_code = err_tree.SubElement(error_message, '{' + ns + '}ErrorCode')  # Create a sub element
    error_code.text = 'Train ID Array Overflow'  # Populate the element text field
    error_code.tail = '\n\t\t\t'

    error_description = err_tree.SubElement(error_message,
                                           '{' + ns + '}ErrorDescription')  # Create a sub element
    error_description.text = 'PLC Array Limit Exceeded'  # Populate the element text field
    error_description.tail = '\n\t\t'

    aa[-1].tail = '\n\t'
    aa.append(ua)  # Append the new element

    return msg


def proc_stomp_msg(msg, fbl, logger):  # Populate the inputs list with data from the message
    for header in msg.headers:
        val = msg.headers[header]
        if header in fbl.outputs:
            if fbl.outputs[header].op_val[0] != val:
                fbl.outputs[header].op_val.clear()
                fbl.outputs[header].op_val.append(val)
                fbl.outputs[header].pub = True
                fbl.pub = True
            else:
                fbl.outputs[header].pub = False
        else:
            ## op_tag, op_ud_mode, op_link, op_comp, op_cval, op_index, op_type
            fbl.outputs[header] = C_Output(header, '0','',None, None, '0', 'string')
            fbl.outputs[header].op_val.append(val)
            fbl.outputs[header].pub = True
            fbl.pub = True

    if fbl.pub:
        pub_mqtt_msg(fbl, create_msg(fbl, logger), logger)  # Publish the data


def create_msg(fb, logger):
    try:
        data_w = out_tree.Element('{' + ns + '}data_w')  # Create a new 'data_w' element
        data_w.tail = '\n\t'

        function_block = out_tree.SubElement(data_w, '{' + ns + '}function_block',
                                            attrib={'name': fb.name,
                                                    'type': fb.type,
                                                    'timestamp':time.asctime()})  # Create a new 'outputs' element
        function_block.tail = '\n\t\t'

        outputs = out_tree.SubElement(function_block, '{' + ns + '}outputs')  # Create a new 'outputs' element
        outputs.tail = '\n\t\t\t'

        for otp in fb.outputs:  # Iterate through the outputs
            if fb.outputs[otp].pub: # If the publishing bit is set..
                if len(fb.outputs[otp].op_val) > 0:  #If the output value is not none    ..
                    new_op = out_tree.SubElement(outputs, '{' + ns + '}output',
                                                attrib={'op_tag': fb.outputs[otp].op_tag,
                                                        'op_type': fb.outputs[otp].op_type})  # Create a sub element
                    new_op.text = str(fb.outputs[otp].op_val[0])  # Set the output tag value
                    new_op.tail = '\n\t\t\t'
                    fb.outputs[otp].pub = False  # Reset the publishing bit

        outputs[-1].tail = '\n\t\t'
        outputs.tail = '\n\t'
        function_block.tail = '\n'

        return err_tree.tostring(data_w, pretty_print=True)  # Convert the etree to a string for publishing

    except Exception as e:
        logger.warning('CreateMessageError={}, FunctionBlock={}'.format(e, fb.name))


def pub_mqtt_msg(fbl, msgb, logger):  # Publishing Thread
    # Write the message to the MQTT Broker
    logger.info('MsgBody={}'.format(msgb))
    key = fbl.name
    mqtt = fbl.mq
    try:
        if mqtt.tl == 1:
            pub_mqtt.single(key, msgb, qos=mqtt.qo,
                            hostname=mqtt.ip,
                            port=mqtt.po, client_id="",
                            keepalive=60,
                            will=None,
                            auth={'username': mqtt.un, 'password': mqtt.pw},
                            tls={}, transport="tcp")
        else:
            pub_mqtt.single(key, msgb, qos=mqtt.qo,
                            hostname=mqtt.ip,
                            port=mqtt.po,
                            client_id="",
                            keepalive=60,
                            will=None,
                            auth={'username': mqtt.un, 'password': mqtt.pw},
                            tls=None, transport="tcp")

        logger.warning('[x] Message Sent, Queue={}'.format(key))

    except Exception as e:
        logger.warning('MQTTPublishError={}, Equip={}'.format(e, key))
