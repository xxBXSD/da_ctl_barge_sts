import time
import threading
import uuid
import paho.mqtt.client as mqttclient
import paho.mqtt.publish as pub_mqtt
from lxml import etree as in_tree
from lxml import etree as out_tree
from lib.common import get_data_itm, C_Input

ns = 'http://www.mesa.org/xml/B2MML'

class write_gac_barge_sts:
    msg_data = {}  # message  dict, consists of tag name as index for (value,type) data [otp]tuple

    def __init__(self, fb, lg):
        self.fbl = fb
        self.logger = lg
        
    def process(self):
        self.logger.info('Processing={}'.format(self.fbl.name))
        th_sql_pub = threading.Thread(target=self.mqtt_con)
        th_sql_pub.start()
        # mqtt_con()


    def on_message(self, client, userdata, message):
        msg = str(message.payload.decode("utf-8"))  # Decode the message into a string
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
            self.logger.debug('ConnectionRefused - server unavailable')
        elif rc == 4:
            self.logger.debug('ConnectionRefused - bad username or password')
        elif rc == 5:
            self.logger.debug('ConnectionRefused - not authorised')
    
    def on_disconnect(self, client, userdata, rc):
        self.logger.debug('DisconnectionMessage={}'.format(rc))
    
    def on_subscribe(self, client, userdata, mid, granted_qos):
        """removes mid values from subscribe list"""
        self.logger.info("Subscribe result={}".format(mid))
    
    def mqtt_con(self):  # Subscribe to the MQTT queue
        cq = self.fbl.mq  # Get the message queue broker details
        mqttc = mqttclient.Client(client_id=self.fbl.name, clean_session=True, userdata=None,
                                  protocol=mqttclient.MQTTv311, transport="tcp")
        if cq.tl == 1:
            mqttc.tls_set()
        # mqttc.enable_self.logger()
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
            client.subscribe(ip_link, qos=0, options=None, properties=None)
    
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
    
            self.process_outputs()  # Call the Write PLC function
    
        except Exception as e:
            self.logger.warning('ProcessMsgError={}, TagName={}'.format(e, self.fbl.name))
    
    def process_outputs(self):
        pub = False # Create a publishing command bit
        # Open the schema file
        try:
            self.ot = out_tree.parse(self.fbl.aux_tags['schema'])  # parse the config file into a tree
            root = self.ot.getroot()  # Get the root
            elem = root.findall(".//*") # get all the elements
            self.logger.info('OpenedSchema={}, FunctionName={}'.format(self.ot, self.fbl.name))
        except Exception as e:
            self.logger.warning('OpenSchemaError={}, FunctionName={}'.format(e, self.fbl.name))
            return
        # Outputs are only published on the first scan and subsequently if the value has changed
        now_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())  # Create a datetime string
        old_val = None
        try:
            if len(self.fbl.outputs) > 0:  # If outputs have been defined in the config file
                for otp in self.fbl.outputs:  # Loop through the outputs
                    tmp_list = []  # Temporary list used to compare the new value with the old value
                    tag = str(self.fbl.outputs[otp].op_tag)  # Get the tag name
                    link = str(self.fbl.outputs[otp].op_link)  # Get the output link (pointer  to the input tag)
                    idx = self.fbl.outputs[otp].op_index  # Get the value list index pointer
                    mode = self.fbl.outputs[otp].op_ud_mode  # Get the update status mode
                    comp = self.fbl.outputs[otp].op_comp  # Get the comparator values list
                    cval = self.fbl.outputs[otp].op_cval  # Get the comparator replacement values list
                    dtype = self.fbl.outputs[otp].op_type   # Get the data type
                    #print('Write_ab_data', tag, link, idx, mode, comp, cval, dtype)
                    if link in self.fbl.inputs:
                        if len(self.fbl.inputs[
                                   link].ip_val) > idx[0]:  # If the link is in the inputs and the index is in the values list
                            val = get_data_itm(self.fbl.inputs[link].ip_val, idx, self.logger)  # From the inputs, get the input value
                            if comp is not None:
                                if str(val) in comp:
                                    val = cval[comp.index(str(val))]
                            tmp_list.append(val)
                            #print('Old Val', self.fbl.outputs[otp].op_val, 'New val', tmp_list)
                            self.fbl.inputs.pop(link)  # Remove the imput from the inputs list so that it is not published next time
                            # unless the next message contains it.
                            if (mode == '0') or (mode == None) or (tmp_list != self.fbl.outputs[otp].op_val):
                                self.fbl.outputs[otp].op_val.clear()  # Clear the value list
                                self.fbl.outputs[otp].op_val.append(val)  # Update the value list
                                self.fbl.outputs[otp].op_time = now_time  # Update the publishing time
                                #self.publish_data(tag, val, dtype)  # Call the write function
                                for itm in elem:  # Iterate through the element s
                                    txt = str(itm.text) # Get the text string
                                    if str(txt) == 'uuid':
                                        itm.text = str(uuid.uuid1())
                                    else:
                                        idx = txt.find(tag) # Look for the tag name in the text
                                        if idx != -1: # If the tag name is found..
                                            itm.text = str(val) # Replace the tag name with the value
                                            #print('Tag is', itm.tag)
                                            if str(itm.tag) == '{http://www.mesa.org/xml/B2MML}ValueString':
                                                pub = True # Set the publishing bit
                            else:
                                self.logger.info('INFO-InputValNone={}, On={} '.format(link, self.fbl.name))
                        else:
                            self.logger.info('INFO-InputValNotFound={}, On={} '.format(link, self.fbl.name))
                    else:
                        self.logger.info('INFO-InputNotFound={}, On={} '.format(link, self.fbl.name))
    
            self.publish_data(pub, elem)
    
        except Exception as e:
            self.logger.warning('WARNING-ProcessOutputsError={}, TagName={}'.format(e, self.fbl.name))
    

    def publish_data(self, pub, elem):
        enable_pub = False
        try:
            if pub:
                for itm in elem:
                    txt = str(itm.text)  # Get the text string
                    #print('Got Text', txt)
                    idx = txt.find("index")  # Look for 'index' in the text
                    if idx != -1:  # If it is found is found..
                        recursive_level = int(txt[5])
                        #print('Reclevel is', recursive_level)
                        self.rec_xml(itm, recursive_level, 0)


                root = self.ot.getroot()
                msgb = out_tree.tostring(root)
                self.pub_mqtt_msg(msgb)

        except Exception as e:
            self.logger.warning('WARNING-PublishDataError={}, TagName={}'.format(e, self.fbl.name))

    def pub_mqtt_msg(self, msgb):  # Publishing Thread
        # Write the message to the remote queue
        key = self.fbl.aux_tags['dest_queue'] # Get the destination queue name
        mqtt = self.fbl.com_dat # Get the broker details from the com_data element

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

            self.logger.warning('[x] Message Sent, Queue={}'.format(key))

        except Exception as e:
            self.logger.warning('WriteMQTTPublishError={}, Equip={}'.format(e, key))

    def rec_xml(self, element, dl, idx):
        parent = element.getparent()
        #print(parent, idx)
        if (idx < dl) and (parent is not None):
            idx += 1
            self.rec_xml(parent, dl, idx)
        else:
            parent.remove(element)