import time
import paho.mqtt.client as mqttclient
from lxml import etree as in_tree
import re
import snap7
#from snap7.types import S7AreaDB
from snap7.types import Areas as areas
import threading
from lib.common import get_data_itm

ns = 'http://www.mesa.org/xml/B2MML'

class C_Input:  # Input Class
    def __init__(self, ip_tag, ip_link, ip_type):
        self.ip_tag = ip_tag
        self.ip_link = ip_link
        self.ip_type = ip_type
        self.ip_val = []


class write_snap7:
    data_types = {}
    data_types['int'] = 'INT'
    data_types['dint'] = 'DWORD'
    data_types['bool'] = 'BOOL'
    data_types['string'] = 'STRING'
    data_types['float'] = 'REAL'
    data_types['real'] = 'REAL'
    msg_data = {}  # message  dict, consists of tag name as index for (value,type) data [otp]tuple

    def __init__(self, fb, lg):
        self.fbl = fb
        self.logger = lg

    def process(self):
        self.logger.info('Processing={}'.format(self.fbl.name))
        th_sql_pub = threading.Thread(target=self.mqtt_con)
        th_sql_pub.start()
        return None

    def on_message(self, client, userdata, message):
        msg = str(message.payload.decode("utf-8"))  # Decode the message into a string
        msg = re.sub(r'\sxmlns="[^"]+"', '', msg, count=1)  # Remove the default namespace
        element = in_tree.fromstring(msg)  # Create a tree element from the message string
        msg = in_tree.ElementTree(element)  # Create an element tree from the element
        self.process_msg(msg)  # Process the message

    def on_connect(self, client, userdata, flags, rc):
        # Get the connection status
        if rc == 0:
            self.logger.info('ConnectionSuccessful={}'.format(rc))
            client.connected_flag = True
            self.mqtt_sub(client)

        elif rc == 1:
            self.logger.debug('ConnectionRefused - incorrect protocol version')
        elif rc == 2:
            self.logger.debug('ConnectionRefused - invalid client identifier')
        elif rc == 3:
            self. logger.debug('ConnectionRefused - server unavailable')
        elif rc == 4:
            self.logger.debug('ConnectionRefused - bad username or password')
        elif rc == 5:
            self.logger.debug('ConnectionRefused - not authorised')

    def on_disconnect(self, client, userdata, rc):
        self.logger.debug('DisconnectionMessage={}'.format(rc))

    def on_subscribe(self, client, userdata, mid, granted_qos):
        """ removes mid values from subscribe list """
        self.logger.info("Subscribe result={}".format(mid))

    def mqtt_con(self):  # Subscribe to the MQTT queue
        cq = self.fbl.mq  # Get the message queue broker details
        mqttc = mqttclient.Client(client_id=self.fbl.name, clean_session=True, userdata=None,
                                  protocol=mqttclient.MQTTv311, transport="tcp")
        if cq.tl == 1:
            mqttc.tls_set()
        mqttc.enable_logger()
        mqttc.username_pw_set(cq.un, cq.pw)
        mqttc.on_message = self.on_message
        mqttc.on_connect = self.on_connect
        mqttc.on_disconnect = self.on_disconnect
        mqttc.on_subscribe = self.on_subscribe

        while not mqttc.is_connected():
            try:
                self.logger.info('Connecting to {}'.format(cq.ip))
                mqttc.connect(cq.ip, port=cq.po, keepalive=60, bind_address="")
                mqttc.loop_forever()
                break
            except Exception as e:
                self.logger.warning('MQTTError={}'.format(e))
                time.sleep(30)

    def mqtt_sub(self, client):
        msg_queue_list = []  # Create a message queue list
        for inp in self.fbl.inputs:  # loop thorough the input items in the function block
            if self.fbl.inputs[inp].ip_link not in msg_queue_list:  # If the input items are not in the message queue list...
                msg_queue_list.append(self.fbl.inputs[inp].ip_link)  # Add them to the list

        for ip_link in msg_queue_list:
            self.logger.info("{}, Subscribing to {}".format(self.fbl.name, ip_link))
            client.subscribe(ip_link, qos=0, options=None, properties=None)

    def open_plc(self):
        try:
            ip = self.fbl.com_dat.ip  # Get the IP address
            rack = self.fbl.com_dat.rk  # Get the PLC Rack
            slot = self.fbl.com_dat.sl  # Get the PLC Slot

            self.fbl.com_dat.cn = snap7.client.Client()
            self.fbl.com_dat.cn.connect(ip, rack, slot)  # Connect to the PLC

            self.logger.info('INFO-Snap7DriverConnectedTo={}'.format(ip))

        except Exception as e:
            self.logger.warning('WARNING-Snap7DriverFailedToConnect={}, Error={}'.format(self.fbl.name, e))

    def process_msg(self, msg):  # Populate the inputs list with data from the message
        try:
            msg_outputs = msg.find('.//{' + ns + '}outputs')  # Get the outputs element
            for msg_output in msg_outputs.iterfind('{' + ns + '}output'):  # Find all the outputs...
                tag = msg_output.get('op_tag')  # Get the output tag name
                dtype = msg_output.get('op_type')  # Get the output data type
                val = msg_output.text  # Get the output value
                if tag not in self.fbl.inputs:  # If the tag does not exist in the inputs
                    ip = C_Input(tag, None, dtype)  # Create a new input instance
                    self.fbl.inputs[tag] = ip  # Add the new instance to the inputs dict
                self.fbl.inputs[tag].ip_val.clear()  # Clear the existing values
                self.fbl.inputs[tag].ip_val.append(val)  # Append the input's value

            self.write_plc()  # Call the Write PLC function

        except Exception as e:
            self.logger.warning('ProcessMsgError={}, TagName={}'.format(e, self.fbl.name))


    def write_plc(self):
        # Outputs are only published on the first scan and subsequently if the value has changed
        now_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())  # Create a datetime string
        tmp_list = []  # Temporary list used to compare the new value with the old value

        try:
            if len(self.fbl.outputs) > 0:  # If outputs have been defined in the config file
                for otp in self.fbl.outputs:  # Loop through the outputs
                    tag = str(self.fbl.outputs[otp].op_tag)  # Get the tag name
                    link = str(self.fbl.outputs[otp].op_link)  # Get the output link (pointer  to the input tag)
                    idx = self.fbl.outputs[otp].op_index  # Get the value list index pointer
                    dtype = self.fbl.outputs[otp].op_type  # Get the data type
                    mode = self.fbl.outputs[otp].op_ud_mode  # Get the update status mode
                    comp = self.fbl.outputs[otp].op_comp  # Get the comparator values list
                    cval = self.fbl.outputs[otp].op_cval  # Get the comparator replacement values list
                    if link in self.fbl.inputs:  # If the link is in the inputs
                        if len(self.fbl.inputs[link].ip_val) > idx[0]:  # And the index is in the values list
                            val = get_data_itm(self.fbl.inputs[link].ip_val,
                                      idx,
                                      self.logger)  # From the inputs, get the input value
                            if val:  # If the new value is not nothing
                                if comp:  # If the new compare value is not nothing
                                    if val in comp:  # If the new value matches any of the compare values
                                        val = cval[comp.index(val)]  # Replace the new value with the relative cval
                                # print('Old Val', self.fbl.outputs[otp].op_val, 'New val', val)
                                tmp_list.append(val)
                                if (mode == '0') or (mode == None) or (tmp_list != self.fbl.outputs[otp].op_val):
                                    self.fbl.outputs[otp].op_val.clear()  # Clear the value list
                                    self.fbl.outputs[otp].op_val.append(val)  # Update the value list
                                    self.fbl.outputs[otp].op_time = now_time  # Update the publishing time
                                    tagl = tag.split(':')

                                    self.write_data(int(tagl[0]), 'DB', int(tagl[1]),
                                               self.data_types[dtype], int(tagl[2]), val)
                            else:
                                self.logger.warning('WARNING-InputValNone={}, On={} '.format(link, self.fbl.name))
                        else:
                            self.logger.warning('WARNING-InputValNotFound={}, On={} '.format(link, self.fbl.name))
                    else:
                        self.logger.info('INFO-InputNotFound={}, On={} '.format(link, self.fbl.name))

            else:  # If no outputs are defined in the config then publish directly from the input tag data
                for inp in self.fbl.inputs:  # Loop through the inputs
                    #  Inputs that came from the message will not have an link value so only publish those inputs
                    if self.fbl.inputs[inp].ip_link is None:
                        tag = self.fbl.inputs[inp].ip_tag  # Get the tag name
                        val = str(self.fbl.inputs[inp].ip_val[0])  # Get the first value in the list
                        if val != 'None':
                            dtype = self.fbl.inputs[inp].ip_type  # get the data type
                            tagl = tag.split(':')
                            self.write_data(int(tagl[0]), 'DB', int(tagl[1]),
                                            self.data_types[dtype], int(tagl[2]), val)

            self.fbl.inputs.clear() # Clear the imputs list

        except Exception as e:
            self.logger.warning('WARNING-WritePLCError={}, TagName={}'.format(e, self.fbl.name))

    def write_data(self, db_num, t_data_type, d_idx, d_type, d_len, d_val):
        #print('Write data', db_num, t_data_type, d_idx, d_type, d_len, d_val)
        if d_val == 'None':
            return
        err_cnt = 0
        try:
            if self.fbl.com_dat.cn is None:  # If there is no connection to the PLC
                self.open_plc()  # Open the PLC connection

            if t_data_type == 'DB':
                if (d_type == 'DWORD') or (d_type == 'DINT'):
                    ba = bytearray(4)
                    snap7.util.set_dword(ba, 0, d_val)
                    # print(ba)
                    while err_cnt <= 5:
                        try:
                            self.fbl.com_dat.cn.write_area(areas['DB'], db_num, d_idx, ba)  # Write the data to the PLC
                            self.logger.info('PLCWrite on DB:{}, Idx={}, Val={}'.format(db_num, d_idx, d_val))
                            break
                        except Exception as e:
                            self.logger.warning('PLCWriteDwordError on DB:{}, Error={}, Retry={}'.format(db_num, e, err_cnt))
                            err_cnt += 1
                            time.sleep(0.1)
                            continue

                elif d_type == 'REAL':
                    ba = bytearray(4)
                    snap7.util.set_real(ba, 0, d_val)
                    # print(ba)
                    while err_cnt <= 5:
                        try:
                            self.fbl.com_dat.cn.write_area(areas['DB'], db_num, d_idx, ba)  # Write the data to the PLC
                            self.logger.info('PLCWrite on DB:{}, Idx={}, Val={}'.format(db_num, d_idx, d_val))
                            break
                        except Exception as e:
                            self.logger.warning('PLCWriteRealError on DB:{}, Error={}, Retry={}'.format(db_num, e, err_cnt))
                            err_cnt += 1
                            time.sleep(0.1)
                            continue

                elif d_type == 'INT':
                    ba = bytearray(2)
                    snap7.util.set_int(ba, 0, d_val)
                    while err_cnt <= 5:
                        try:
                            self.fbl.com_dat.cn.write_area(areas['DB'], db_num, d_idx, ba)  # Write the data to the PLC
                            self.logger.info('PLCWrite on DB:{}, Idx={}, Val={}'.format(db_num, d_idx, d_val))
                            break
                        except Exception as e:
                            self.logger.warning('PLCWriteIntError on DB:{}, Error={}, Retry={}'.format(db_num, e, err_cnt))
                            err_cnt += 1
                            time.sleep(0.1)
                            continue

                elif d_type == 'STRING':
                    ba = bytearray(int(d_len))
                    snap7.util.set_string(ba, 0, d_val, d_len)
                    while err_cnt <= 5:
                        try:
                            self.fbl.com_dat.cn.write_area(areas['DB'], db_num, d_idx, ba)  # Write the data to the PLC
                            self.logger.info('PLCWrite on DB:{}, Idx={}, Val={}'.format(db_num, d_idx, d_val))
                            break
                        except Exception as e:
                            self.logger.warning('PLCWriteStringError on DB:{}, Error={}, Retry={}'.format(db_num, e, err_cnt))
                            err_cnt += 1
                            time.sleep(0.1)
                            continue

        except Exception as e:
            self.logger.warning('Snap7WriteDataError={}'.format(e))