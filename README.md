## Vihio

This program bridges your Palazzetti stove box with Home Assistant.

It uses Home Assistant MQTT discovery mechanism: https://www.home-assistant.io/docs/mqtt/discovery/ 

Checkout the project, either edit ```config/default.yml``` or create a ```config/local.yml``` with the properties you need to override. ```api_username``` and ```api_username``` are your Hi-Kumo app credentials. Then run ```Vihio.py```.

Please use, clone and improve. Some things are not supported. It was tested only with my own devices and installation. This is a very early release, based on reverse engineering of the network traffic. I have no relation to Hitachi (other than using their product) and they may not like it. Use at your own perils.

## Installation

### Setup MQTT discovery on HA
You will need an MQTT broker: [MQTT broker](https://www.home-assistant.io/docs/mqtt/broker/)

And to activate MQTT discovery: [MQTT discovery](https://www.home-assistant.io/docs/mqtt/discovery/)

### Clone the Vihio repo
```
git clone https://www.github.com/dotvav/vihio.git
cd vihio
pip3 install -r requirements.txt
```

### Change the configuration
You can either update the ```config/default.yml``` file or create a new file named ```config/local.yml```. The keys that are present in the local config will override the ones in the default config. If a key is absent from local config, Vihio will fallback to the value of the default config. I recommend keeping the default config as is and make all the changes in the local config file so that you don't lose them when the default file gets updated from git.

Property | Usage | Note
--- | --- | ---
**`devices`** | an array of device definitions | **Required**. Each device needs a `name` which is human friendly and a `hostname` which is the ip address or the hostname that the device uses on the network.   
`mqtt_discovery_prefix` | the MQTT topic prefix that HA is monitoring for discovery | You should probably not touch this. HA's default is `homeassistant`. 
`mqtt_state_prefix` | the MQTT topic prefix that Vihio will use to broadcast the devices state to HA | You should probably not touch this.
`mqtt_command_prefix` | the MQTT topic prefix that Vihio will listen to for HA commands | You should probably not touch this.
`mqtt_reset_topic` | the MQTT topic where Vihio receives reset commands | Send any message on this topic to tell Aasivak it must re-register all the devices. You should create an automation to do that every time HA starts.
**`mqtt_host`** | the host name or ip address of the MQTT broker | Use `localhost` or `127.0.0.1` if the MQTT broker runs on the same machine as Vihio.
`mqtt_client_name` | the name that Vihio will us on MQTT | You should probably not touch this.
`mqtt_username` | the MQTT broker username | This is needed only if the MQTT broker requires an authenticated connection.
`mqtt_password` | the MQTT broker password | This is needed only if the MQTT broker requires an authenticated connection.
`refresh_delays` | list of waiting durations before calling the box API to refresh devices state | If you set `[2, 5, 10, 30]` then Vihio will call the Hi-Kumo API to refresh its state after 2s, then 5s, then 10s, and then every 30s. The delay is reset to 2s when Vihio receives a command from HA. Some randomness is added to these delays: every time Vihio needs to wait, it adds or remove up to `logging_delay_randomness/2` to the delay. 
`refresh_delay_randomness` | maximum number of seconds to add to all the waiting durations | See `refresh_delays`. Use `0` for no randomness.
`logging_level` | Vihio's logging level | INFO


### Start Vihio manually
```
python3 Vihio.py
```

### Start Vihio as a systemd service
Create the following ```/etc/systemd/system/vihio.service``` file (change the paths as required):

```
[Unit]
Description=Vihio
Documentation=https://github.com/dotvav/vihio
After=network.target

[Service]
Type=simple
User=homeassistant
WorkingDirectory=/home/homeassistant/vihio
ExecStart=/usr/bin/python3 /home/homeassistant/vihio/Vihio.py
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

Run the following to enable and run the service, and see what its status is:
```
sudo systemctl enable vihio.service
sudo systemctl start vihio.service
sudo systemctl status vihio.service
```

## Dependencies

- requests
- paho-mqtt
- pyyaml


