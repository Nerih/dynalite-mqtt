import os

LOG_LEVEL = os.getenv("LOG_LEVEL", "ERROR")
PDEG_HOST = os.getenv("PDEG_HOST", "")
PDEG_PORT = int(os.getenv("PDEG_PORT", 50000))
DYNET_RATE_LIMIT = int(os.getenv("DYNET_RATE_LIMIT", 0))
MAX_BUFFER_SIZE = int(os.getenv("MAX_BUFFER_SIZE", 256))
MQTT_HOST = os.getenv("MQTT_HOST", "")
MQTT_PORT = int(os.getenv("MQTT_PORT", 1883))
MQTT_USERNAME = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD = os.getenv("MQTT_PASSWORD", "")
MQTT_TOPIC_PREFIX = os.getenv("MQTT_TOPIC_PREFIX", "dynalite")