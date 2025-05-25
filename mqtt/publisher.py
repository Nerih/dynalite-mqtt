import paho.mqtt.client as mqtt
import json
from datetime import datetime
from typing import Callable, Optional

class MQTTPublisher:
    

    
    def __init__(
        self,
        #loop,
  
        mqtt_username,
        mqtt_password,
        mqtt_port,
        mqtt_host,
        will_topic=None,
        will_payload="offline",
        will_qos=0,
        will_retain=True,
        on_connect=None,
        on_disconnect=None,
        on_message=None,
        logger: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize MQTT client with optional callbacks and LWT.

        :param coolmaster_client: Reference to the CoolMaster client
        :param loop: Asyncio event loop
        :param will_topic: Last Will and Testament topic
        :param will_payload: Payload for LWT
        :param will_qos: QoS level for LWT
        :param will_retain: Whether the LWT message should be retained
        :param on_connect: Optional user-defined callback for connect event
        :param on_disconnect: Optional user-defined callback for disconnect event
        :param on_message: Optional user-defined callback for incoming MQTT messages
        """
        #self.loop = loop
        self.client = mqtt.Client()

        # Authentication
        self.client.username_pw_set(mqtt_username, mqtt_password)

        # Callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        # External user-defined callbacks
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self.on_message = on_message

        self.will_topic = will_topic
        self.will_retain = will_retain

        #logging
        self.logger = logger or (lambda msg: print(f"{datetime.now().strftime('%H:%M:%S')} 📡🧾 MQTT Client:{msg}"))


        # Set Last Will and Testament (LWT)
        if will_topic:
            self.client.will_set(
                topic=will_topic,
                payload=will_payload,
                qos=will_qos,
                retain=will_retain
            )


        # Try to connect
        try:
            self.log(f"🔌 Connecting to MQTT at {mqtt_host}:{mqtt_port}...")
            self.client.connect(mqtt_host, mqtt_port, keepalive=60)
            self.client.loop_start()
        except Exception as e:
            self.log(f"❌ TCP connect error: {e}")

    def log(self, msg: str):
        self.logger(msg)

    def _on_connect(self, client, userdata, flags, rc):
        """
        Internal callback for MQTT connection event.
        Calls external callback if provided.
        """
        if rc == 0:
            self.log(f" ✅ connected successfully")
            if hasattr(self, "will_topic") and self.will_topic:
                self.client.publish(self.will_topic, "online", retain=self.will_retain)

            if self.on_connect:
                self.on_connect(client, userdata, flags, rc)
        elif rc == 4:
            self.log(f"❌ authentication failed (bad username/password)")
        else:
            self.log(f"❌ connection failed with result code {rc}")

    def _on_disconnect(self, client, userdata, rc):
        """
        Internal callback for MQTT disconnection event.
        Calls external callback if provided.
        """
        self.log(f"⚠️ Disconnected from MQTT (code {rc})")
        if self.on_disconnect:
            self.on_disconnect(client, userdata, rc)

    def _on_message(self, client, userdata, msg):
        """
        Internal callback for incoming MQTT messages.
        Calls external callback if provided.
        """
        try:
            topic = msg.topic
            payload = msg.payload.decode()
            self.log(f"📨 command: {topic} = {payload}")

            # Pass to external handler
            if self.on_message:
                self.on_message(topic, payload)

        except Exception as e:
            self.log(f"❌ Error processing MQTT message: {e}")

    def publish(self, topic: str, payload, qos=0, retain=False) -> bool:
        """
        Publish a message to MQTT with error handling.

        :param topic: Topic to publish
        :param payload: Payload (dict or str)
        :param qos: QoS level
        :param retain: Retain flag
        :return: True if published, False otherwise
        """
        try:
            # If dict or object, serialize to JSON
            if not isinstance(payload, str):
                payload = json.dumps(payload)
            result = self.client.publish(topic, payload=payload, qos=qos, retain=retain)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self.log(f"📤 Published to topic: {topic}")
                return True
            else:
                self.log(f" ❌  Failed to publish to {topic}, rc={result.rc}")
                return False
        except Exception as e:
            self.log(f" ❌ Exception during publish to {topic}: {e}")
            return False

    def subscribe(self, topic: str, qos=0):
        """
        Subscribe to a topic.

        :param topic: Topic string
        :param qos: QoS level
        """
        try:
            self.client.subscribe(topic, qos=qos)
            self.log(f"📡 Subscribed to {topic}")
        except Exception as e:
            self.log(f"❌ Subscription error for {topic}: {e}")

    def stop(self):
        """
        Cleanly stop the MQTT client.
        """
        try:
            self.log(f"🔌 Stopping...")
            self.client.loop_stop()
            self.client.disconnect()
        except Exception as e:
            self.log(f"❌ Error while stopping: {e}")
