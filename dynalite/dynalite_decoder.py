import xml.etree.ElementTree as ET
from typing import List, Union
from datetime import datetime
from typing import NamedTuple

class DecodeResult(NamedTuple):
    message: str
    no_error: bool
    template: str
    fields:  List[Union[int, str]]
    
class DynetDecoder:
    def __init__(self, xml_path: str):
        self.tree = ET.parse("dynalite/dynalite_messages.xml")
        self.root = self.tree.getroot()

    def decode_dynet1_packet(self, packet: bytes) -> tuple[str, bool]:
        if len(packet) != 8:
            return "❌ Invalid packet length", False, "",[]

        bStatus = True    

        header = packet[0]
        opcode = packet[3]

        proto_root = self.root.find(f".//MessagePrototype[@Byte='0'][@Opcode='0x{header:02x}']")
        if proto_root is None:
            return f"❓ Unknown Dynet1 header: 0x{header:02X}", False, "",[]

        sub_proto = None
        for mp in proto_root.findall("MessagePrototype"):
            if mp.get("Byte") != "3":
                continue
            opcode_hex = mp.get("Opcode")
            range_end_hex = mp.get("OpcodeRangeEnd")
            if not opcode_hex:
                continue
            opcode = int(opcode_hex, 16)
            if range_end_hex:
                opcode_end = int(range_end_hex, 16)
                if opcode <= packet[3] <= opcode_end:
                    sub_proto = mp
                    break
            elif opcode == packet[3]:
                sub_proto = mp
                break

        if sub_proto is None:
                    return f"❓ Unknown Dynet1 Opcode: 0x{packet[3]:02X}", False, "",[]

        byte2_value = packet[2]
        for mp in sub_proto.findall("MessagePrototype"):
            if mp.get("Byte") != "2":
                continue
            opcode_hex = mp.get("Opcode")
            range_end_hex = mp.get("OpcodeRangeEnd")
            if not opcode_hex:
                continue
            opcode = int(opcode_hex, 16)
            if range_end_hex:
                opcode_end = int(range_end_hex, 16)
                if opcode <= byte2_value <= opcode_end:
                    sub_proto = mp
                    break
            elif opcode == byte2_value:
                sub_proto = mp
                break


        name = sub_proto.findtext("Name", default="#Todo")
        brief = sub_proto.findtext("VerboseFormatString")
        fields = self._parse_fields(sub_proto, packet)

        try:
            description = brief.format(*fields) if brief else name
        except Exception as e:
            description = f"⚠️ Format error: {e}"
            bStatus = False

        return f"{name} → {description}", bStatus, brief,fields

    def _parse_fields(self, proto: ET.Element, packet: bytes) -> List[Union[int, str]]:
        field_values = []
        indexed_fields = {}

        for field in proto.findall("Field"):
            try:
                value = 0
                for byte_def in field.findall("Byte"):
                    pos = int(byte_def.text, 0)
                    if pos >= len(packet):
                        continue
                    byte_val = packet[pos]
                    bitmask = int(byte_def.get("BitMask", "0xff"), 16)
                    offset = int(byte_def.get("Offset", "0"))
                    mult_raw = byte_def.get("Multiplier", "1")
                    try:
                        multiplier = float.fromhex(mult_raw) if "0x" in mult_raw.lower() else float(mult_raw)
                    except ValueError:
                        multiplier = 1.0
                    value += ((byte_val & bitmask) >> offset) * multiplier

                mes_type = field.get("MesType", "")
                if mes_type == "MES_PERIOD_20MS":
                    value = round(value * 0.02, 2)
                elif mes_type == "MES_PRESET":
                    #if it is Dynet 2 return value
                    if packet[0] == 0xAC:
                        value += value
                     #if it is Dynet 1 map using banks
                    else:
                        opcode = packet[3]
                        bank = packet[5]
                        if opcode in (0X00, 0X01, 0X02, 0X03) :
                            preset = (bank*8) + opcode
                        elif opcode in (0X0A, 0X0B, 0X0C, 0X0D):
                            preset = (bank*8) + (opcode -6)
                        else:
                            #default usually for 0x65 or 0x6B which don't use banks
                            value +=value 
                        value = preset +1
                    #map common presets
                    preset_map = {1: "High (1)", 2: "Medium (2)", 3: "Low (3)", 4: "Off (4)"}
                    value = preset_map.get(value,value) 
                elif mes_type == "MES_TEMPERATURE_VALUE_DYNET1Q7DOT8":
                    high = packet[int(field.find("Byte").text)]
                    low = packet[int(field.findall("Byte")[1].text)]
                    value = round(high + (low / 100.0), 2)
                elif mes_type == "MES_TEMPERATURE_VALUE_DYNET1Q8DOT8":
                    high = packet[int(field.find("Byte").text)]
                    low = packet[int(field.findall("Byte")[1].text)]
                    value = round(((high << 8) | low) / 256.0, 2)
                elif mes_type == "MES_HEX_2DIGIT_DECIMAL_VALUE":
                    if not isinstance(value, (int, float)):
                        raise TypeError(f"MES_HEX_2DIGIT_DECIMAL_VALUE expected int/float, got {type(value)}")
                    value = f"{int(value):02X}"
                elif mes_type == "MES_MONTH_DOW_VALUE":
                    raw = int(value)
                    dow = (raw >> 4) & 0x0F
                    month = raw & 0x0F
                    value = f"Month:{month} DOW:{['Mon','Tue','Wed','Thu','Fri','Sat','Sun'][dow-1] if 1 <= dow <= 7 else 'Invalid'}"
                elif mes_type in ("MES_RANGE_MIN", "MES_RANGE_MAX", "MES_DEVICE", "MES_CHANNEL", "MES_BOX_SOURCE", "MES_BOX_TARGET", "MES_BOX", "MES_AREA", "MES_NUMERIC_VALUE", "MES_DEV_NUMBER_DYNET2"):
                    value = int(value)
                elif mes_type in ("MES_DEVICE_SOURCE", "MES_DEVICE_TARGET", "MES_SYNC", "MES_JOIN", "MES_D1_CHECKSUM"):
                    value = f"{int(value):02X}"
                elif mes_type in ("MES_LOGICAL_LEVEL"):
                    value = f"{100 - round((value / 255.0) * 100)}%"
                elif mes_type in ("MES_DYNET2_LOGICAL_LEVEL"):
                    value = f"{round((value / 255.0) * 100)}%"
                elif mes_type == ("MES_D2_SERIAL_NUMBER"):
                    value = int.from_bytes(packet[10:13], byteorder='big')
                else:
                    if mes_type:
                        #base_type = field.get("BaseType", "").lower()
                        #if base_type == "int":
                        #    value = int(value)
                        #elif base_type == "float":
                        #    value = float(value)
                        #elif base_type == "hex":
                        #    value = f"{int(value):02X}"
                        #elif base_type:
                        #    print(f"{datetime.now().strftime('%H:%M:%S')}       ├─ ℹ️  Unknown BaseType: {base_type}")
                        #else:
                            print(f"{datetime.now().strftime('%H:%M:%S')}       ├─ ℹ️  Unhandled MesType: {mes_type}")

                index = int(field.get("index", len(indexed_fields)))
                indexed_fields[index] = value

            except Exception as e:
                print(f"⚠️ Error parsing field: {e}, mes_type:{field.get('MesType')}")
                index = int(field.get("index", len(indexed_fields)))
                indexed_fields[index] = "<err>"

        # Return as a list in index order
        max_index = max(indexed_fields.keys(), default=-1)
        field_values = [indexed_fields.get(i, "<unset>") for i in range(max_index + 1)]
        return field_values

    def decode_dynet2_packet(self, packet: bytes)  -> tuple[str, bool]:
        if len(packet) < 6 or packet[0] != 0xAC:
            return "❌ Invalid Dynet2 packet", False, "",[]
        bStatus = True
        header = packet[0]
        length_byte = packet[1]
        expected_len = (length_byte * 4) + 4
        if len(packet) != expected_len:
            return f"❌ Packet length mismatch (expected {expected_len}, got {len(packet)})", False, "",[]

        # Start with root opcode (Byte 0)
        proto_root = self._find_matching_proto(self.root, 0, packet[0])
        if proto_root is None:
            return f"❓ Unknown Dynet2 header: 0x{packet[0]:02X}", False, "",[]

        # Recursively walk opcode tree: Byte=2 → Byte=9 → Byte=10 etc.
        current_proto = proto_root
        for byte_index in [2, 9, 10]:
            sub_proto = self._find_matching_proto(current_proto, byte_index, packet[byte_index] if byte_index < len(packet) else None)
            if sub_proto is None:
                break
            current_proto = sub_proto

        name = current_proto.findtext("Name", default="#Todo")
        brief = current_proto.findtext("VerboseFormatString")
        fields = self._parse_fields(current_proto, packet)

        try:
            description = brief.format(*fields) if brief else name
        except Exception as e:
            description = f"⚠️ Format error: {e}"
            bStatus = False
        return f"{name} → {description}", bStatus,brief,fields




    def _find_matching_proto(self, parent: ET.Element, byte_index: int, value: int) -> Union[ET.Element, None]:
        if value is None:
            return None
        for mp in parent.findall("MessagePrototype"):
            if mp.get("Byte") != str(byte_index):
                continue
            opcode_hex = mp.get("Opcode")
            range_end_hex = mp.get("OpcodeRangeEnd")
            if not opcode_hex:
                continue
            opcode_start = int(opcode_hex, 16)
            if range_end_hex:
                opcode_end = int(range_end_hex, 16)
                if opcode_start <= value <= opcode_end:
                    return mp
            elif opcode_start == value:
                return mp
        return None



    @classmethod
    def decode(cls, packet: bytes) -> DecodeResult:
        if not cls._instance:
            cls._instance = cls("dynalite_messages.xml")
        if  len(packet) == 8:
            result = cls._instance.decode_dynet1_packet(packet)
            return DecodeResult(result[0],result[1],result[2],result[3])
        elif packet[0] == 0xAC:
            result = cls._instance.decode_dynet2_packet(packet)
            return DecodeResult(result[0],result[1],result[2],result[3])
        return DecodeResult("❌ Unknown Dynet packet format",False, "", [])

    _instance = None