import asyncio
from datetime import datetime
from config import PDEG_HOST, PDEG_PORT, MQTT_HOST,MQTT_PORT,MQTT_USERNAME,MQTT_PASSWORD,MQTT_TOPIC_PREFIX,DYNET_RATE_LIMIT,LOG_LEVEL
from dynalite.dynalite_client import DynetClient
from dynalite.dynalite_decoder import DynetDecoder
from mqtt.publisher import MQTTPublisher
import json
import logging
import sys

# Basic logger
#def log(msg: str):
#    print(f"{datetime.now().strftime('%H:%M:%S')} 🧠 {msg}")

# ───────────────────────────────────────────────
# Logging setup
# ───────────────────────────────────────────────
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s.%(msecs)03d %(message)s',
    datefmt='%H:%M:%S',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("🔌 MQTT Bridge")


# Entry point for async application
async def main():
    logger.info("Dynalite → MQTT Bridge starting...")

    # Instantiate DynetClient
    dynet = DynetClient(PDEG_HOST, PDEG_PORT, logger=logger,send_rate_limit=DYNET_RATE_LIMIT)
    # Instantiate MQTT Client
    mqtt_client = MQTTPublisher(mqtt_username=MQTT_USERNAME,mqtt_password=MQTT_PASSWORD,mqtt_host=MQTT_HOST,mqtt_port=MQTT_PORT,will_topic=f"{MQTT_TOPIC_PREFIX}/status")
    mqtt_client.subscribe(f"{MQTT_TOPIC_PREFIX}/set")

    # Async connection callback
    async def on_dynet_connect():
        logger.info("🌐 Connected — ready to receive Dynet packets")
        # You can call dynet.send_logical(...) here to test
        # Example: dynet.send_logical(area=10, command=0x4A, data1=0x0C, data2=25, data3=0, join=0xFF)
        #dynet.send_dynet2([0x80,0xDA,0x00,0x01,0x4C,0x00,0x27,0x0A],bDecode=True)
        #recall_preset_high(dynet,14,0.5,0XFF)
        
    # Main handler callback for incoming packets
    def handle_dynet_message(packet_type: str, raw: bytes, parsed: dict):
        hex_string = ' '.join(f"{b:02X}" for b in raw)
        decode = DynetDecoder.decode(raw)
        logger.info(f"       └─ 💬 {decode.message}")

        # 🔗 Place to publish parsed data to MQTT
        # Example:
        # mqtt.publish(topic=f"dynalite/{packet_type}", payload=json.dumps(parsed))
        packet_payload = {
            "type": f"{packet_type}",
            "description" :f"{decode.message}",
            "hex_string": f"{hex_string}",
            "byte_array" :f"{list(raw)}",
            "template": decode.template,
            "fields": decode.fields,   
            "field_types" : decode.field_types
        }
        # Publish packet data, but do not retain
        if mqtt_client.client.is_connected:
            mqtt_client.publish(topic=f"{MQTT_TOPIC_PREFIX}", payload=json.dumps(packet_payload),retain=False)
        else:    
            logger.error("❌ MQTT not connected, cannot Publish DYNET message to MQTT")


    def handle_mqtt_command(topic, payload):
        if not dynet.is_connected:
            logger.error("⚠️ DYNET not connected, cannot send DYNET message from MQTT")
            return
        
        try:
            try:
                data = json.loads(payload)
            except json.JSONDecodeError as e:
                raise SyntaxError(f"❌ Invalid JSON: {e}")        
             # Validate expected structure
            packet_type = data.get("type")
            hex_string = data.get("hex_string")
            byte_array = data.get("byte_array")     
            if not packet_type:
                raise KeyError("❌ Missing 'type' in payload")
            if not hex_string and not byte_array:
                raise KeyError("❌ Must provide either 'hex_string' or 'byte_array'")
            
            # Optionally get a response ID
            response_id = data.get("response_id")
            if not response_id:
                logger.warning("X NO RESPONSE_ID SUPPLIED")
                _publishfail("Warning: no response_id supplied", response_id=None)
                #return  # Important: early return to prevent processing untracked commands

            # Convert hex string to bytes
            if hex_string:
                try:
                    raw = bytes.fromhex(hex_string.replace(" ", ""))
                except ValueError as e:
                    raise TypeError(f"❌ Invalid hex_string: {e}")
            # Convert byte_array (as stringified list) to bytes
            elif byte_array:
                try:
                    if isinstance(byte_array, str):
                        byte_array = json.loads(byte_array)
                    if not isinstance(byte_array, list) or not all(isinstance(b, int) and 0 <= b <= 255 for b in byte_array):
                        raise ValueError("byte_array must be a list of integers 0–255")
                    raw = bytes(byte_array)
                except Exception as e:
                    raise TypeError(f"❌ Invalid byte_array: {e}")
            # Decide based on type
            if packet_type.lower() == "dynet1":
                #commented out as you must not compute checksum OR pre-pend 1C. 
                if len(raw) != 7:
                    raise TypeError(f"❌ Dynet1 packets must be exactly 7 bytes, include 1c, but not the checksum, got len={len(raw)} raw=[{' '.join(f'{b:02X}' for b in raw)}]")                
                dynet.send_logical(area=raw[1],data1=raw[2],command=raw[3],data2=raw[4],data3=raw[5],join=raw[6],bDecode=True)
                #log(f"📤 Sent Dynet1 packet: {' '.join(f'{b:02X}' for b in raw)}")
                _publishsuccess(response_id)
            elif packet_type.lower() == "dynet2":
                #library will handle any type errors
                #if raw[0] != 0xAC:
                #    raise TypeError("❌ Dynet2 packet must start with 0xAC")
            
                #dynet.writer.write(raw)
                dynet.send_dynet2(raw,bDecode=True)
                _publishsuccess(response_id)

            elif packet_type.lower() == "physical":
                if len(raw) != 8 or raw[0] != 0x5C:
                    raise TypeError("❌ Physical Dynet1 packet must start with 0x5C and be 8 bytes long")
            
                #dynet.writer.write(raw)
                logger.info(f"📤 Sent Physical Dynet1 packet: {' '.join(f'{b:02X}' for b in raw)}")
                _publishsuccess(response_id)
            else:
                raise LookupError(f"❌ Unknown packet type: {packet_type}")
        except Exception as e:
            logger.error(f"⚠️ Error handling MQTT {MQTT_TOPIC_PREFIX}/Set -> Dynet: {e}")
            # Publish packet data, but do not retain
            if mqtt_client.client.is_connected:
                _publishfail(e,response_id)
            else:    
                logger.error("❌ MQTT not connected, cannot Publish Error Message")
            return

    def _publishfail(e, response_id=None):
        payload = {
            "status": f"Error handling MQTT {MQTT_TOPIC_PREFIX}/Set -> Dynet: {e}"
        }
        if response_id:
            payload["response_id"] = response_id
            mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/set/res/{response_id}", json.dumps(payload), retain=False)
        mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/set/res", json.dumps(payload), retain=False)


    def _publishsuccess(response_id=None):
        payload = {
            "status": "OK"
        }
        if response_id:
            payload["response_id"] = response_id
            mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/set/res/{response_id}", json.dumps(payload), retain=False)
        mqtt_client.publish(f"{MQTT_TOPIC_PREFIX}/set/res", json.dumps(payload), retain=False)



    # Assign handlers
    dynet.on_connect = on_dynet_connect
    dynet.on_message = handle_dynet_message
    mqtt_client.on_message = handle_mqtt_command

    try:
        await dynet.connect()
        logger.info("🔁 Listening for packets. Press Ctrl+C to exit.")
        while True:
            await asyncio.sleep(1)  # Passive loop

    except asyncio.CancelledError:
        logger.info("⏹ Cancelled by asyncio.")

    except KeyboardInterrupt:
        logger.info("🛑 Stopped by user.")

    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")

    finally:
        dynet.stop()
        await asyncio.sleep(0.5)
        logger.info("🔍 Shutdown complete.")

# Bootstrap runner
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.error(f"❌ Fatal startup error: {e}")
