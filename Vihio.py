import json
import random
import time
import logging

import paho.mqtt.client as mqtt
import requests
import yaml


################

class Device:

    # Based on the Android app mapping: https://pastebin.com/VQjYtzAn
    status_names = {
        0: "Off",
        1: "Timer-regulated switch off",
        10: "Switch off",
        1000: "General error – See Manual",
        1001: "General error – See Manual",
        11: "Burn pot cleaning",
        12: "Cooling in progress",
        1239: "Door open",
        1240: "Temperature too high",
        1241: "Cleaning warning",
        1243: "Fuel error – See Manual",
        1244: "Pellet probe or return water error",
        1245: "T05 error Disconnected or faulty probe",
        1247: "Feed hatch or door open",
        1248: "Safety pressure switch error",
        1249: "Main probe failure",
        1250: "Flue gas probe failure",
        1252: "Too high exhaust gas temperature",
        1253: "Pellets finished or Ignition failed",
        1508: "General error – See Manual",
        2: "Ignition test",
        3: "Pellet feed",
        4: "Ignition",
        5: "Fuel check",
        50: "Final cleaning",
        501: "Off",
        502: "Ignition",
        503: "Fuel check",
        504: "Operating",
        505: "Firewood finished",
        506: "Cooling",
        507: "Burn pot cleaning",
        51: "Ecomode",
        6: "Operating",
        7: "Operating - Modulating",
        8: "-",
        9: "Stand-By"
    }
    is_heating_statuses = [2, 3, 4, 5, 502, 503, 504, 51, 6, 7]

    def __init__(self, house, device_id, name, hostname):
        self.house = house
        self.device_id = device_id
        self.name = name
        self.hostname = hostname
        self.climate_discovery_topic = None
        self.climate_mqtt_config = None
        self.status_sensor_discovery_topic = None
        self.status_sensor_mqtt_config = None
        self.exit_temp_sensor_discovery_topic = None
        self.exit_temp_sensor_mqtt_config = None
        self.fumes_temp_sensor_discovery_topic = None
        self.fumes_temp_sensor_mqtt_config = None
        self.pellet_qty_sensor_discovery_topic = None
        self.pellet_qty_sensor_mqtt_config = None
        self.target_temperature = None
        self.room_temperature = None
        self.exit_temperature = None
        self.fumes_temperature = None
        self.pellet_quantity = None
        self.status = None
        self.mode = None
        self.topic_to_func = None

    def update_state(self, data):
        self.target_temperature = data["SETP"]
        self.room_temperature = data["T1"]
        self.exit_temperature = data["T2"]
        self.fumes_temperature = data["T3"]
        self.pellet_quantity = float(data["PQT"])
        self.status = self.status_names.get(data["LSTATUS"], "Off")
        self.mode = "heat" if data["LSTATUS"] in self.is_heating_statuses else "off"

    def update_mqtt_config(self):
        self.climate_discovery_topic = self.house.config.mqtt_discovery_prefix + "/climate/" + self.device_id + "/config"
        self.climate_mqtt_config = {
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
            self.climate_mqtt_config["mode_command_topic"]: self.send_mode,
            self.climate_mqtt_config["temperature_command_topic"]: self.send_target_temperature,
        }
        self.status_sensor_discovery_topic = self.house.config.mqtt_discovery_prefix + "/sensor/" + self.device_id + "_status/config"
        self.status_sensor_mqtt_config = {
            "name": self.name + " (status)",
            "state_topic": self.house.config.mqtt_state_prefix + "/" + self.device_id + "/status"
        }
        self.exit_temp_sensor_discovery_topic = self.house.config.mqtt_discovery_prefix + "/sensor/" + self.device_id + "_exit_temp/config"
        self.exit_temp_sensor_mqtt_config = {
            "name": self.name + " (exit temperature)",
            "device_class": "temperature",
            "unit_of_measurement": self.house.config.temperature_unit,
            "state_topic": self.house.config.mqtt_state_prefix + "/" + self.device_id + "/exit_temp"
        }
        self.fumes_temp_sensor_discovery_topic = self.house.config.mqtt_discovery_prefix + "/sensor/" + self.device_id + "_fumes_temp/config"
        self.fumes_temp_sensor_mqtt_config = {
            "name": self.name + " (fumes temperature)",
            "device_class": "temperature",
            "unit_of_measurement": self.house.config.temperature_unit,
            "state_topic": self.house.config.mqtt_state_prefix + "/" + self.device_id + "/fumes_temp"
        }
        self.pellet_qty_sensor_discovery_topic = self.house.config.mqtt_discovery_prefix + "/sensor/" + self.device_id + "_pellet_qty/config"
        self.pellet_qty_sensor_mqtt_config = {
            "name": self.name + " (pellet quantity)",
            "unit_of_measurement": self.house.config.pellet_quantity_unit,
            "state_topic": self.house.config.mqtt_state_prefix + "/" + self.device_id + "/pellet_qty"
        }

    def register_mqtt(self, discovery):
        mqtt_client = self.house.mqtt_client

        mqtt_client.subscribe(self.climate_mqtt_config["mode_command_topic"], 0)
        mqtt_client.subscribe(self.climate_mqtt_config["temperature_command_topic"], 0)

        if discovery:
            mqtt_client.publish(self.climate_discovery_topic, json.dumps(self.climate_mqtt_config), qos=1, retain=True)
            mqtt_client.publish(self.status_sensor_discovery_topic, json.dumps(self.status_sensor_mqtt_config), qos=1, retain=True)
            mqtt_client.publish(self.exit_temp_sensor_discovery_topic, json.dumps(self.exit_temp_sensor_mqtt_config), qos=1, retain=True)
            mqtt_client.publish(self.fumes_temp_sensor_discovery_topic, json.dumps(self.fumes_temp_sensor_mqtt_config), qos=1, retain=True)
            mqtt_client.publish(self.pellet_qty_sensor_discovery_topic, json.dumps(self.pellet_qty_sensor_mqtt_config), qos=1, retain=True)

    def unregister_mqtt(self, discovery):
        mqtt_client = self.house.mqtt_client

        mqtt_client.unsubscribe(self.climate_mqtt_config["mode_command_topic"], 0)
        mqtt_client.unsubscribe(self.climate_mqtt_config["temperature_command_topic"], 0)

        if discovery:
            mqtt_client.publish(self.climate_discovery_topic, None, qos=1, retain=True)
            mqtt_client.publish(self.status_sensor_discovery_topic, None, qos=1, retain=True)
            mqtt_client.publish(self.exit_temp_sensor_discovery_topic, None, qos=1, retain=True)
            mqtt_client.publish(self.fumes_temp_sensor_discovery_topic, None, qos=1, retain=True)
            mqtt_client.publish(self.pellet_qty_sensor_discovery_topic, None, qos=1, retain=True)

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
            mqtt_client.publish(self.climate_mqtt_config["current_temperature_topic"], self.room_temperature, retain=True)
            mqtt_client.publish(self.climate_mqtt_config["mode_state_topic"], self.mode, retain=True)
            mqtt_client.publish(self.climate_mqtt_config["temperature_state_topic"], self.target_temperature, retain=True)
            mqtt_client.publish(self.status_sensor_mqtt_config["state_topic"], self.status, retain=True)
            mqtt_client.publish(self.exit_temp_sensor_mqtt_config["state_topic"], self.exit_temperature, retain=True)
            mqtt_client.publish(self.fumes_temp_sensor_mqtt_config["state_topic"], self.fumes_temperature, retain=True)
            mqtt_client.publish(self.pellet_qty_sensor_mqtt_config["state_topic"], self.pellet_quantity, retain=True)


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
    temperature_unit = "°C"
    pellet_quantity_unit = "kg"

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
        self.temperature_unit = raw.get("temperature_unit",self.temperature_unit)
        self.pellet_quantity_unit = raw.get("pellet_quantity_unit", self.pellet_quantity_unit)


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

        if response is None:
            status_code = -1
        else:
            status_code = response.status_code

        if status_code != 200:
            if retry > 0:
                logging.debug("API call failed with status code {}. Retrying.", status_code)
                time.sleep(self.delayer.next())
                return self.get_api(url, retry - 1)
            else:
                logging.debug("API call failed with status code {}. No more retry.", status_code)
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
        with open("config/default.yml", 'r', encoding="utf-8") as yml_file:
            raw_default_config = yaml.safe_load(yml_file)

        try:
            with open("config/local.yml", 'r', encoding="utf-8") as yml_file:
                raw_local_config = yaml.safe_load(yml_file)
                raw_default_config.update(raw_local_config)
        except IOError:
            logging.info("No local config file found")

        return Config(raw_default_config)

    def register_all(self):
        self.mqtt_client.loop_start()
        self.mqtt_client.subscribe(self.config.mqtt_reset_topic, 0)
        for device_id, device in self.devices.items():
            device.register_mqtt(True)
        self.mqtt_client.on_message = self.on_message

    def unregister_all(self):
        self.mqtt_client.on_message(None)
        self.mqtt_client.unsubscribe(self.config.mqtt_reset_topic, 0)
        for device_id, device in self.devices.items():
            device.unregister_mqtt(True)
        self.mqtt_client.loop_stop()

    def update_all_states(self):
        for device_cfg in self.config.devices:
            raw_device = self.palazzetti.fetch_state(device_cfg["hostname"])
            try:
                device_id = raw_device["DATA"]["MAC"].replace(':', '_')
            except KeyError:
                logging.error("Device response payload is missing a MAC identifier")
                logging.debug("Payload received: %s", json.dumps(raw_device))
                return
            if device_id in self.devices:
                device = self.devices[device_id]
            else:
                device = Device(self, device_id,  device_cfg["name"], device_cfg["hostname"])
                self.devices[device.device_id] = device
            device.update_state(raw_device["DATA"])

    def refresh_all(self):
        self.update_all_states()
        for device in self.devices.values():
            device.publish_state()

    def setup(self):
        self.update_all_states()
        for device in self.devices.values():
            device.update_mqtt_config()
            logging.info("Device found: %s (%s | %s)", device.name, device.device_id, device.hostname)

    def loop_start(self):
        self.setup()
        self.register_all()
        while True:
            self.refresh_all()
            time.sleep(self.delayer.next())

    def on_message(self, client, userdata, message):
        if message.topic == self.config.mqtt_reset_topic:
            self.setup()
            self.register_all()
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
