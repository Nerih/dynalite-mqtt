import asyncio
from datetime import datetime
from typing import Callable, Optional
from dynalite.dynalite_decoder import DynetDecoder
from config import MAX_BUFFER_SIZE
import logging
logger = logging.getLogger("🔌 MQTT Bridge")

def calc_checksum(packet: list[int]) -> int:
    return (-sum(packet) & 0xFF)

def fletcher16(data: bytes) -> int:
    sum1 = 0
    sum2 = 0
    for b in data:
        sum1 = (sum1 + b) % 256
        sum2 = (sum2 + sum1) % 256
    return (sum2 << 8) | sum1

class DynetClient:
    def __init__(self, host: str = "192.168.0.251", port: int = 50001, reconnect_delay: int = 1, send_rate_limit: int = 20, logger: Optional[Callable[[str], None]] = None):
        self.host = host
        self.port = port
        self.reconnect_delay = reconnect_delay
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self._stop = False
        self._connected = asyncio.Event()
        self._task: Optional[asyncio.Task] = None
        #logging.infoger = logger or (lambda msg: print(f"{datetime.now().strftime('%H:%M:%S')} 🧠 {msg}"))
        self.on_connect: Optional[Callable[[], None]] = None
        self.on_disconnect: Optional[Callable[[], None]] = None
        self.on_message: Optional[Callable[[str, bytes, dict], None]] = None
        self._send_queue: asyncio.Queue = asyncio.Queue()
        self._send_task: Optional[asyncio.Task] = None
        self.send_rate_limit = send_rate_limit


    @property
    
    def is_connected(self) -> bool:
        """Public property to check if the client is currently connected."""
        return self._connected.is_set()


    async def _send_worker(self):
        while not self._stop:
            try:
                packet = await self._send_queue.get()
            except Exception as e:
                logging.error(f"❌ Failed to get packet from queue: {e}")
                await asyncio.sleep(0.1)
                continue

            try:
                if self.writer:
                    try:
                        self.writer.write(packet)
                        await self.writer.drain()
                        logging.info(f"       └─ ✅ Sent Dynet: {' '.join(f'{b:02X}' for b in packet)}")
                    except Exception as e:
                        logging.error(f"❌ Failed to write packet: {e}")
                else:
                    logging.error("⚠️ Not connected — dropped packet")
            except Exception as e:
                logging.error(f"❌ Unexpected send error: {e}")

            try:
                if self.send_rate_limit > 0:
                    delay = 1 / self.send_rate_limit
                    await asyncio.sleep(delay)
            except Exception as e:
                logging.error(f"❌ Error during rate limiting delay: {e}")



    #def log(self, msg: str):
    #    logging.infoger(msg)

    async def connect(self):
        self._task = asyncio.create_task(self._connection_loop())
        self._send_task = asyncio.create_task(self._send_worker())
    
    async def _connection_loop(self):
        while not self._stop:
            try:
                self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
                self._connected.set()
                logging.info(f"✅ Connected to Dynet IP at {self.host}:{self.port}")
                if self.on_connect:
                    await self.on_connect()
                await self._listen()
            except Exception as e:
                logging.error(f"❌ Dynet IP Connection error: {e}")
                self._connected.clear()
            logging.warning(f"🔄 Dynet IP Reconnecting in {self.reconnect_delay} seconds...")
            await asyncio.sleep(self.reconnect_delay)

    async def _listen(self):
        buffer = bytearray()
        try:
            while not self._stop:
                
                chunk = await self.reader.read(MAX_BUFFER_SIZE) #CHANGED to read from ENV
                if not chunk:
                    logging.warning("🔌 Connection closed by Dynet")
                    break
                buffer += chunk
              
                # Immediately after appending chunk, enforce buffer size limit from above
                if len(buffer) >= MAX_BUFFER_SIZE:
                    logging.error(f"⚠️ Buffer overflow detected ({len(buffer)} bytes). Clearing buffer to resync.")
                    buffer.clear()
                    continue  # Skip further processing until new data arrives
                
                while buffer:
                    if buffer[0] == 0x1C and len(buffer) >= 8:
                        packet = buffer[:8]
                        if packet[7] == calc_checksum(packet[:7]):
                            logging.info(f"🔜 Dynet1 (Logical): {' '.join(f'{b:02X}' for b in packet)}")
                            if self.on_message:
                                self.on_message("dynet1", packet, {"header": packet[0], "command": packet[3]})
                            buffer = buffer[8:]
                            continue

                    elif buffer[0] == 0x5C and len(buffer) >= 8:
                        packet = buffer[:8]
                        if packet[7] == calc_checksum(packet[:7]):
                            logging.info(f"🔧 Dynet1 (Physical): {' '.join(f'{b:02X}' for b in packet)}")
                            if self.on_message:
                                self.on_message("dynet1-physical", packet, {"header": packet[0], "command": packet[3]})
                            buffer = buffer[8:]
                            continue

                    elif buffer[0] == 0x6C and len(buffer) >= 8:
                        packet = buffer[:8]
                        if packet[7] == calc_checksum(packet[:7]):
                            try:
                                text = bytes(packet[1:7]).decode("ascii", errors="replace")
                            except Exception:
                                text = "<decode error>"
                            logging.info(f"💬 Dynet1 (Debug): {' '.join(f'{b:02X}' for b in packet)} → \"{text}\"")
                            if self.on_message:
                                self.on_message("dynet1-debug", packet, {"text": text})
                            buffer = buffer[8:]
                            continue

                    elif buffer[0] == 0xAC and len(buffer) >= 4:
                        length = buffer[1] * 4
                        total_length = 2 + length + 2
                        if len(buffer) >= total_length:
                            packet = buffer[:total_length]
                            cs = fletcher16(packet[:-2])
                            expected = int.from_bytes(packet[-2:], 'big')
                            if cs == expected:
                                logging.info(f"🌐 Dynet2: {' '.join(f'{b:02X}' for b in packet)}")
                                if self.on_message:
                                    self.on_message("dynet2", packet, {"length": length})
                                buffer = buffer[total_length:]
                                continue
                            else:
                                logging.critical(f"⚠️ Invalid checksum! Got {cs:04X}, expected {expected:04X} → packet: {' '.join(f'{b:02X}' for b in packet)}")
                                buffer = buffer[1:]
                                continue

                    else:
                        logging.critical(f"⚠️ Desync or unknown header at {buffer[0]:02X}, dropping byte")
                        buffer = buffer[1:]
                        continue

                    break
        except Exception as e:
            logging.error(f"❌ Listen error: {e}")
        finally:
            self._connected.clear()
            if self.writer:
                self.writer.close()
                await self.writer.wait_closed()
            self.reader = self.writer = None
            if self.on_disconnect:
                await self.on_disconnect()

    def send_logical(self, area: int, command: int, data1: int, data2: int, data3: int, join: int, bDecode: bool = True) :
        #try:
        #when calling this function, please enclose in try/except
        packet = [0x1C, area, data1, command, data2, data3, join]
        packet.append(calc_checksum(packet))
        if bDecode:
            result = DynetDecoder.decode(packet)
            if not result.no_error:
                raise Exception(f"🚫 Packet did not decode successfully — {result.message}")
        if self.writer:
            self._send_queue.put_nowait(bytearray(packet))
            logging.info(f"📤 Queued Dynet1 Logical: {' '.join(f'{b:02X}' for b in packet)}")
            if bDecode:
                logging.info(f"       └─ 💬 {result.message}")
        else:
            raise Exception("⚠️ Cannot send — not connected.")
        #except Exception as e:
        #    logging.info(f"❌ Send error: {e}")

    def send_physical(self, area: int, command: int, data1: int, data2: int, data3: int, join: int, bDecode: bool = True):
        #try:
        #when calling this function, please enclose in try/except
        packet = [0x5C, area, data1, command, data2, data3, join]
        packet.append(calc_checksum(packet))
        if bDecode:
            result = DynetDecoder.decode(packet)
            if not result.no_error:
                raise Exception(f"🚫 Packet did not decode successfully — {result.message}")
        if self.writer:
            self._send_queue.put_nowait(bytearray(packet))
            logging.info(f"📤 Queued Dynet1 Physical: {' '.join(f'{b:02X}' for b in packet)}")
            if bDecode:
                logging.info(f"       └─ 💬 {result.message}")
        else:
            logging.critical("⚠️ Cannot send — not connected.")
        #except Exception as e:
        #    logging.info(f"❌ Send error: {e}")

    def send_dynet2(self, payload: list[int], bDecode: bool = True):
        #try:
        if isinstance(payload, bytes):
            payload = list(payload)

        if not payload:
            raise Exception("❌ Empty Dynet2 payload")

        # Case A: Full framed packet starting with 0xAC
        if payload[0] == 0xAC and len(payload) >= 6:
            length_field = payload[1]
            expected_payload_len = (length_field * 4) + 4  # AC + len + data + 2-byte checksum
            if len(payload) == expected_payload_len:
                # Check checksum
                cs_actual = fletcher16(bytearray(payload[:-2]))
                cs_expected = (payload[-2] << 8) | payload[-1]
                if cs_actual == cs_expected:
                    # ✅ Valid full packet
                    final_packet = payload
                else:
                    raise Exception(f"❌ Checksum mismatch: got {cs_actual:04X}, expected {cs_expected:04X}")
            else:
                raise Exception(f"❌ Invalid framed packet length: expected {expected_payload_len}, got {len(payload)}")
        else:
            # Case B: Treat as unframed payload, build full packet
            data = payload
            length = len(data) // 4
            header = [0xAC, length]
            final_packet = header + data
            cs = fletcher16(bytearray(final_packet))
            final_packet += [cs >> 8, cs & 0xFF]

        # Decode (optional)
        if bDecode:
            result = DynetDecoder.decode(final_packet)
            if not result.no_error or "#Todo" in result.message:
                raise Exception(f"🚫 Packet did not decode successfully — {result.message}")

        # Send via queue
        if self.writer:
            self._send_queue.put_nowait(bytearray(final_packet))
            logging.info(f"📤 Queued Dynet2: {' '.join(f'{b:02X}' for b in final_packet)}")
            if bDecode:
                logging.info(f"       └─ 💬 {result.message}")
        else:
            logging.critical("⚠️ Cannot send — not connected.")
        #except Exception as e:
        #    logging.info(f"❌ Send Dynet2 error: {e}")


    def stop(self):
        self._stop = True
        if self._task:
            self._task.cancel()
