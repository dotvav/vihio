import json
import random
import time
import logging

import paho.mqtt.client as mqtt
import requests
import yaml


################

class Device:
    def __init__(self, house, device_id, name, hostname):
        self.house = house
        self.device_id = device_id
        self.name = name
        self.hostname = hostname
        self.discovery_topic = None
        self.mqtt_config = None
        self.target_temperature = None
        self.temperature = None
        self.mode = None

    def update_state(self, data):
        self.target_temperature = data["SETP"]
        self.temperature = data["T1"]
        self.mode = "heat" if data["STATUS"] else "off"

    def update_mqtt_config(self):
        self.discovery_topic = self.house.config.mqtt_discovery_prefix + "/climate/" + self.device_id + "/config"
        self.mqtt_config = {
            "name": self.name,
            "unique_id": self.device_id,

            "current_temperature_topic": self.house.config.mqtt_state_prefix + "/" + self.device_id + "/temp",
            "mode_state_topic": self.house.config.mqtt_state_prefix + "/" + self.device_id + "/mode",
            "temperature_state_topic": self.house.config.mqtt_state_prefix + "/" + self.device_id + "/target_temp",

            "mode_command_topic": self.house.config.mqtt_command_prefix + "/" + self.device_id + "/mode",
            "temperature_command_topic": self.house.config.mqtt_command_prefix + "/" + self.device_id + "/target_temp",

            "modes": ["off", "heat"],
            "device": {"identifiers": self.device_id, "manufacturer": "Palazzetti"}
        }
        self.topic_to_func = {
            self.mqtt_config["mode_command_topic"]: self.send_mode,
            self.mqtt_config["temperature_command_topic"]: self.send_target_temperature,
        }

    def register_mqtt(self, discovery):
        mqtt_client = self.house.mqtt_client

        mqtt_client.subscribe(self.mqtt_config["mode_command_topic"], 0)
        mqtt_client.subscribe(self.mqtt_config["temperature_command_topic"], 0)

        if discovery:
            mqtt_client.publish(self.discovery_topic, json.dumps(self.mqtt_config))

    def unregister_mqtt(self, discovery):
        mqtt_client = self.house.mqtt_client

        mqtt_client.unsubscribe(self.mqtt_config["mode_command_topic"], 0)
        mqtt_client.unsubscribe(self.mqtt_config["temperature_command_topic"], 0)

        if discovery:
            mqtt_client.publish(self.discovery_topic, None)

    def on_message(self, topic, payload):
        func = self.topic_to_func.get(topic, None)
        if func is not None:
            func(payload)

    def send_mode(self, payload):
        self.house.palazzetti.set_power_state(self.hostname, payload == "heat")

    def send_target_temperature(self, target_temperature):
        self.house.palazzetti.set_target_temperature(self.hostname, target_temperature)

    def publish_state(self):
        mqtt_client = self.house.mqtt_client
        if mqtt_client is not None:
            mqtt_client.publish(self.mqtt_config["current_temperature_topic"], self.temperature)
            mqtt_client.publish(self.mqtt_config["mode_state_topic"], self.mode)
            mqtt_client.publish(self.mqtt_config["temperature_state_topic"], self.target_temperature)


################

class Config:
    devices = None
    api_user_agent = 'vihio'
    mqtt_discovery_prefix = "homeassistant"
    mqtt_state_prefix = "palazzetti/state"
    mqtt_command_prefix = "palazzetti/command"
    mqtt_reset_topic = "palazzetti/reset"
    mqtt_host = "127.0.0.1"
    mqtt_port = 1883
    mqtt_username = None
    mqtt_password = None
    mqtt_client_name = "vihio"
    logging_level = "INFO"
    refresh_delays = [3, 5, 10, 30]
    refresh_delay_randomness = 2

    def __init__(self, raw):
        self.devices = raw.get("devices")
        self.mqtt_discovery_prefix = raw.get("mqtt_discovery_prefix", self.mqtt_discovery_prefix)
        self.mqtt_state_prefix = raw.get("mqtt_state_prefix", self.mqtt_state_prefix)
        self.mqtt_command_prefix = raw.get("mqtt_command_prefix", self.mqtt_command_prefix)
        self.mqtt_reset_topic = raw.get("mqtt_reset_topic", self.mqtt_reset_topic)
        self.mqtt_host = raw.get("mqtt_host", self.mqtt_host)
        self.mqtt_port = raw.get("mqtt_port", self.mqtt_port)
        self.mqtt_username = raw.get("mqtt_username", self.mqtt_username)
        self.mqtt_password = raw.get("mqtt_password", self.mqtt_password)
        self.mqtt_client_name = raw.get("mqtt_client_name", self.mqtt_client_name)
        self.logging_level = raw.get("logging_level", self.logging_level)
        self.refresh_delays = raw.get("refresh_delays", self.refresh_delays)
        self.refresh_delay_randomness = raw.get("refresh_delay_randomness", self.refresh_delay_randomness)


################

class PalazzettiAdapter:
    def __init__(self):
        self.delayer = Delayer([1], 2)
        self.session = requests.Session()

    def get_api(self, url, retry=1):
        logging.debug("API call: %s", url)
        try:
            response = self.session.get(url=url, data=None, headers=None)
        except Exception as e:
            logging.warning(e)
            response = None

        if response is None or response.status_code != 200:
            if retry > 0:
                logging.debug("API call failed. Retrying.")
                time.sleep(self.delayer.next())
                return self.get_api(url, retry - 1)
            else:
                logging.debug("API call failed. No more retry.")
                return {}
        else:
            logging.debug("API response: %s", response.text)
            return json.loads(response.text)

    def send_command(self, hostname, command):
        return self.get_api("http://{}/cgi-bin/sendmsg.lua?cmd={}".format(hostname, command))

    def fetch_state(self, hostname):
        return self.send_command(hostname, "GET ALLS")

    def set_power_state(self, hostname, power_state):
        return self.send_command(hostname, "CMD {}".format(("ON", "OFF")[power_state]))

    def set_target_temperature(self, hostname, target_temperature):
        return self.send_command(hostname, "SET SETP {}".format(target_temperature))


################

class Delayer:
    def __init__(self, delays, randomness):
        self.delays = delays
        self.delay_index = 0
        self.randomness = randomness

    def reset(self):
        self.delay_index = 0

    def next(self):
        delay = self.delays[self.delay_index] + self.randomness * (random.random() - .5)
        self.delay_index = min(len(self.delays) - 1, self.delay_index + 1)
        return delay


################

class House:
    def __init__(self):
        self.config = self.read_config()
        logging.basicConfig(level=self.config.logging_level, format="%(asctime)-15s %(levelname)-8s %(message)s")
        self.mqtt_client = mqtt.Client(self.config.mqtt_client_name)
        if self.config.mqtt_username is not None:
            self.mqtt_client.username_pw_set(self.config.mqtt_username, self.config.mqtt_password)
        self.mqtt_client.connect(self.config.mqtt_host, self.config.mqtt_port)
        self.devices = {}
        self.delayer = Delayer(self.config.refresh_delays, self.config.refresh_delay_randomness)
        self.palazzetti = PalazzettiAdapter()

    @staticmethod
    def read_config():
        with open("config/default.yml", 'r') as yml_file:
            raw_default_config = yaml.safe_load(yml_file)

        try:
            with open("config/local.yml", 'r') as yml_file:
                raw_local_config = yaml.safe_load(yml_file)
                raw_default_config.update(raw_local_config)
        except IOError:
            logging.info("No local config file found")

        return Config(raw_default_config)

    def register_all(self):
        self.mqtt_client.subscribe(self.config.mqtt_reset_topic, 0)
        for device_id, device in self.devices.items():
            device.register_mqtt(True)
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.loop_start()

    def unregister_all(self):
        self.mqtt_client.on_message(None)
        self.mqtt_client.loop_stop()
        self.mqtt_client.unsubscribe(self.config.mqtt_reset_topic, 0)
        for device_id, device in self.devices.items():
            device.unregister_mqtt(True)

    def refresh_all(self):
        for device_cfg in self.config.devices:
            raw_device = self.palazzetti.fetch_state(device_cfg["hostname"])
            device_id = raw_device["DATA"]["MAC"].replace(':', '_')
            if device_id in self.devices:
                device = self.devices[device_id]
            else:
                device = Device(self, device_id,  device_cfg["name"], device_cfg["hostname"])
                self.devices[device.device_id] = device
            device.update_state(raw_device["DATA"])
            device.publish_state()

    def setup(self):
        for device_cfg in self.config.devices:
            raw_device = self.palazzetti.fetch_state(device_cfg["hostname"])
            device_id = raw_device["DATA"]["MAC"].replace(':', '_')
            if device_id in self.devices:
                device = self.devices[device_id]
            else:
                device = Device(self, device_id, device_cfg["name"], device_cfg["hostname"])
                self.devices[device.device_id] = device
            device.update_state(raw_device["DATA"])
            device.update_mqtt_config()
            logging.info("Device found: %s (%s | %s)", device.name, device.device_id, device.hostname)

    def loop_start(self):
        self.setup()
        self.register_all()
        while True:
            time.sleep(self.delayer.next())
            self.refresh_all()

    def on_message(self, client, userdata, message):
        if message.topic == self.config.mqtt_reset_topic:
            self.setup()
            return

        topic_tokens = message.topic.split('/')
        # TODO validation

        device_id = topic_tokens[len(topic_tokens) - 2]
        command = topic_tokens[len(topic_tokens) - 1]
        value = str(message.payload.decode("utf-8"))
        logging.info("MQTT message received device '" + device_id + "' command '" + command + "' value '" + value + "'")

        device = self.devices.get(device_id, None)
        if device is not None:
            device.on_message(message.topic, value)
        self.delayer.reset()


################

House().loop_start()
