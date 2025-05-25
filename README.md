# 🧠 Dynalite → MQTT Bridge

This Python-based tool acts as a real-time **bridge between Philips Dynalite lighting systems and MQTT**, enabling seamless smart home integration with platforms like **Home Assistant**.

---

## 🚀 Features

- Listens to Dynet (Dynalite) traffic over TCP via PDEG or similar interface
- Decodes Dynet1, Dynet2, and Physical Dynet1 packets
- Publishes decoded data to MQTT in structured JSON
- Subscribes to MQTT `set` topics to send control commands to Dynalite
- Built-in logging with emoji-enhanced logs for clarity 🧠📡💬

---

## 🛠 Requirements

- Python 3.9+
- Dynalite PDEG (or other Dynet-over-IP interface)
- Running MQTT broker (e.g., Mosquitto)
- Home Assistant (optional)

---

## 📦 Installation

```bash
git clone https://github.com/yourusername/dynalite-mqtt
cd dynalite-mqtt
pip install -r requirements.txt
⚙️ Configuration
Edit the config.py file:

python
PDEG_HOST = "192.168.x.x"
PDEG_PORT = 50001

MQTT_HOST = "192.168.x.x"
MQTT_PORT = 1883
MQTT_USERNAME = "yourusername"
MQTT_PASSWORD = "yourpassword"
MQTT_TOPIC_PREFIX = "dynalite/bridge"
▶️ Running the Bridge
bash
Copy
Edit
python3 main.py
You should see output like:

makefile
12:34:56 🧠 Dynalite → MQTT Bridge starting...
12:34:57 🌐 Connected — ready to receive Dynet packets
12:34:58        └─ 💬 Area 10, Channel 5 Recall level 100% with fade 0.5s
📨 MQTT Integration
Incoming Dynet Packets → MQTT
Published to: dynalite/bridge

Payload format:

json
{
  "type": "dynet1",
  "description": "Area 1, Channel 5 Recall level 80%...",
  "hex_string": "1C 0A 00 4A 0C 1F FF E2",
  "byte_array": "[28, 10, 0, 74, 12, 31, 255, 226]"
}
Outgoing MQTT Commands → Dynet
Subscribe to: dynalite/bridge/set

Payload format:

json
{
  "type": "dynet1",
  "hex_string": "1C 0A 00 4A 0C 1F FF E2"
}
OR

json
{
  "type": "dynet2",
  "byte_array": [172, 0, 0, 1, 76, 0, 39, 10]
}
Return Topic:
dynalite/bridge/set/return will receive either:

✅ {"status": "OK"}

❌ {"status": "Error handling MQTT..."}

📚 Project Structure
.
├── main.py               # Async bridge runner
├── config.py             # IPs and credentials
├── mqtt/
│   └── publisher.py      # MQTT publish/subscribe wrapper
├── dynalite/
│   ├── dynalite_client.py    # Dynet TCP client
│   └── dynalite_decoder.py  # Dynet packet decoder
🧪 Testing
You can use MQTT tools (like MQTT Explorer or mosquitto_pub) to test sending packets via:

mosquitto_pub -h MQTT_HOST -t dynalite/bridge/set -m '{"type": "dynet1", "hex_string": "1C 0A 00 4A 0C 1F FF E2"}'
🧠 Emoji Legend
Emoji	Meaning
🧠	Log from main bridge logic
📡	MQTT activity
💬	Decoded Dynet message
📤	Packet sent to Dynet
❌	Error condition
✅	Successful action
⚠️	Warning or fallback
🔁	Listening for packets

🛡 Disclaimer
This bridge assumes familiarity with Philips Dynalite systems and MQTT. Use at your own risk, and always test changes before deploying to production.

📄 License
MIT License

🤝 Contributions
Feel free to fork, raise issues, and submit PRs! 💡