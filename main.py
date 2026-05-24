import bluetooth
import machine
import time
import network
import json
import os
import struct
from micropython import const
from ble_advertising import advertising_payload

try:
    led = machine.Pin("LED", machine.Pin.OUT)
except ValueError:
    led = machine.Pin(8, machine.Pin.OUT)

def _read_temp():
    try:
        adc = machine.ADC(4)
        raw = adc.read_u16()
        volt = raw * 3.3 / 65535
        t = 27 - (volt - 0.706) / 0.001721
        return round(t, 1) if -10 < t < 125 else 0.0
    except:
        return 0.0

_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE = const(3)

_UART_UUID = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
_UART_TX = (bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E"), bluetooth.FLAG_NOTIFY)
_UART_RX = (bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E"), 0x08 | 0x04)
_UART_SERVICE = (_UART_UUID, (_UART_TX, _UART_RX))

RECORD_SIZE = const(6)

class DataLogger:
    def __init__(self):
        self.rec_count = 0
        self.max_records = 0
        self.start_time = 0
        self.running = False
        self.timer = None
        self.period_ms = 5000
        self._calc_storage()
        self._count_existing()

    def _calc_storage(self):
        try:
            vfs = os.statvfs("/")
            free = vfs[0] * vfs[2]
            self.max_records = (free // 2) // RECORD_SIZE
        except:
            self.max_records = 5000

    def _count_existing(self):
        try:
            sz = os.stat("data.bin")[6]
            self.rec_count = sz // RECORD_SIZE
            if self.rec_count >= self.max_records:
                os.remove("data.bin")
                self.rec_count = 0
        except:
            self.rec_count = 0

    def start(self, period_ms=5000):
        if self.running:
            return
        self.period_ms = period_ms
        self.running = True
        self.start_time = time.time()
        self._count_existing()
        try:
            self.timer = machine.Timer(-1)
        except ValueError:
            self.timer = machine.Timer(0)
        self.timer.init(period=self.period_ms, mode=machine.Timer.PERIODIC, callback=lambda t: self._record())

    def set_period(self, seconds):
        was_running = self.running
        if was_running:
            self.stop()
        self.period_ms = max(1, int(seconds)) * 1000
        if was_running:
            self.running = False  # allow start() to proceed
            self.start(self.period_ms)

    def stop(self):
        self.running = False
        if self.timer:
            self.timer.deinit()
            self.timer = None

    def _record(self):
        if not self.running or self.rec_count >= self.max_records:
            return
        elapsed = int(time.time() - self.start_time)
        temp_c = _read_temp()
        temp_int = int(temp_c * 100)
        freq = machine.freq() // 1000000
        data = struct.pack("<HhH", elapsed, temp_int, freq)
        try:
            with open("data.bin", "ab") as f:
                f.write(data)
            self.rec_count += 1
        except:
            pass

    def get_stats(self):
        try:
            vfs = os.statvfs("/")
            free = vfs[0] * vfs[2]
        except:
            free = 0
        max_bytes = free // 2
        max_recs = max_bytes // RECORD_SIZE
        used = self.rec_count * RECORD_SIZE
        remain_recs = max_recs - self.rec_count
        remain_days = remain_recs * 5 // 86400 if remain_recs > 0 else 0
        return {
            "used": used,
            "max_bytes": max_bytes,
            "records": self.rec_count,
            "max_records": max_recs,
            "remaining_days": remain_days,
            "running": self.running,
        }

    def get_csv(self):
        out = "elapsed_s,temperature_C,freq_MHz\n"
        try:
            with open("data.bin", "rb") as f:
                while True:
                    b = f.read(RECORD_SIZE)
                    if len(b) < RECORD_SIZE:
                        break
                    sec, tc, fm = struct.unpack("<HhH", b)
                    out += f"{sec},{tc/100:.2f},{fm}\n"
        except:
            pass
        return out


class DeviceManager:
    def __init__(self, ble):
        self._ble = ble
        self._ble.active(True)
        self._ble.irq(self._irq)
        ((self._handle_tx, self._handle_rx),) = self._ble.gatts_register_services((_UART_SERVICE,))
        self._connections = set()
        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)
        self.cmd_buffer = ""
        self.logger = DataLogger()
        self.logger.start()
        self.mqtt = None
        self.device_id = self._load_device_id()
        self.load_and_connect()
        self._advertise()

    def _load_device_id(self):
        try:
            with open("config.json") as f:
                return json.load(f).get("device_id", "PicoW")
        except:
            return "PicoW"

    def _irq(self, event, data):
        if event == _IRQ_CENTRAL_CONNECT:
            self._connections.add(data[0])
        elif event == _IRQ_CENTRAL_DISCONNECT:
            self._connections.discard(data[0])
            self._advertise()
        elif event == _IRQ_GATTS_WRITE:
            if data[1] == self._handle_rx:
                msg = self._ble.gatts_read(self._handle_rx).decode().strip()
                self.handle_chunk(msg)

    def handle_chunk(self, chunk):
        if chunk == "END":
            self.process_final_command(self.cmd_buffer)
            self.cmd_buffer = ""
        else:
            self.cmd_buffer += chunk

    def process_final_command(self, cmd):
        if cmd == "SCAN":
            self.scan_wifi()
        elif cmd.startswith("W:"):
            try:
                ssid, pw = cmd[2:].split(",")
                self.save_config(ssid, pw)
                self.connect_wifi(ssid, pw)
            except:
                self.send_notify("ERR:Format Error")
        elif cmd == "1":
            led.value(1)
            self.send_notify("LED:ON")
        elif cmd == "0":
            led.value(0)
            self.send_notify("LED:OFF")
        elif cmd == "LOGSTART":
            self.logger.start()
            self.send_notify("LOG:STARTED")
        elif cmd == "LOGSTOP":
            self.logger.stop()
            self.send_notify("LOG:STOPPED")
        elif cmd == "STATUS":
            self.report_status()
        elif cmd == "CSV":
            csv = self.logger.get_csv()
            self.send_notify("CSVSTART:" + str(len(csv)))
            for i in range(0, len(csv), 14):
                self.notify("CSVD:" + csv[i : i + 14])
                time.sleep_ms(30)
            self.send_notify("CSVEND")
        elif cmd == "DELDATA":
            try:
                os.remove("data.bin")
                self.logger.rec_count = 0
                self.send_notify("DELDATA:OK")
            except:
                self.send_notify("DELDATA:ERR")
        elif cmd == "WIFISTATUS":
            self.report_wifi()
        elif cmd == "DEVINFO":
            self.report_devinfo()
        elif cmd.startswith("MQTTSET:"):
            self.mqtt_connect(cmd[8:])
        elif cmd == "MQTTDIS":
            self.mqtt_disconnect()
        elif cmd == "MQTTST":
            self.report_mqtt()
        elif cmd.startswith("SETPERIOD:"):
            try:
                sec = int(cmd[10:])
                self.logger.set_period(sec)
                self.send_notify("SETPERIOD:OK:" + str(sec))
            except:
                self.send_notify("SETPERIOD:ERR")
        elif cmd == "MQTTTEST":
            self.mqtt_test()
        elif cmd.startswith("SETDEVID:"):
            self.set_device_id(cmd[9:])

    def notify(self, text):
        data = text.encode() if isinstance(text, str) else text
        for conn in self._connections:
            self._ble.gatts_notify(conn, self._handle_tx, data)

    def send_notify(self, text):
        self.notify(text)

    def notify_multi(self, *msgs):
        for m in msgs:
            self.notify(m)
            time.sleep_ms(30)

    def report_status(self):
        s = self.logger.get_stats()
        self.notify_multi(
            "STUSED:" + str(s["used"]),
            "STMAX:" + str(s["max_bytes"]),
            "STREC:" + str(s["records"]),
            "STDAYS:" + str(s["remaining_days"]),
        )

    def report_wifi(self):
        if self.wlan.isconnected():
            cfg = self.wlan.ifconfig()
            self.notify_multi(
                "WISSID:" + self.wlan.config("ssid"),
                "WIIP:" + cfg[0],
                "WIGW:" + cfg[2],
                "WIRSSI:" + str(self.wlan.status("rssi")),
            )
        else:
            self.notify("WIRSSI:-200")

    def set_device_id(self, new_id):
        new_id = new_id.strip()
        if not new_id:
            self.send_notify("DEVID:ERR")
            return
        try:
            c = {}
            if "config.json" in os.listdir():
                with open("config.json") as f:
                    c = json.load(f)
            c["device_id"] = new_id
            with open("config.json", "w") as f:
                json.dump(c, f)
            self.device_id = new_id
            self._advertise()   # 重新廣播新名稱
            self.send_notify("DEVID:OK:" + new_id)
        except:
            self.send_notify("DEVID:ERR")

    def report_devinfo(self):
        import gc
        temp_c = round(_read_temp(), 1)
        gc.collect()
        freq = machine.freq() // 1000000
        mem_alloc = gc.mem_alloc()
        mem_free = gc.mem_free()
        self.notify_multi(
            "DTEMP:" + str(temp_c),
            "DFREQ:" + str(freq),
            "DMEM:" + str(mem_alloc) + "," + str(mem_free),
            "DEVID:" + self.device_id,
        )
        # 若 MQTT 已連線，順便 publish 裝置資訊
        if self.mqtt:
            self._publish_devinfo(temp_c, freq, mem_alloc, mem_free)

    def _get_mqtt_topic(self):
        try:
            with open("config.json") as f:
                return json.load(f).get("mqtt_topic", "picow")
        except:
            return "picow"

    def _publish_devinfo(self, temp_c, freq, mem_alloc, mem_free):
        if not self.ensure_mqtt():
            return
        try:
            base = self._get_mqtt_topic()
            payload = ('{"id":"' + self.device_id + '"' +
                       ',"temp":' + str(temp_c) +
                       ',"freq":' + str(freq) +
                       ',"mem_alloc":' + str(mem_alloc) +
                       ',"mem_free":' + str(mem_free) + '}')
            self.mqtt.publish(base + "/device", payload)
        except:
            self.mqtt = None

    def mqtt_connect(self, params):
        parts = params.split(",", 4)
        if len(parts) < 5:
            self.notify("MQTT:ERR")
            return
        broker, port, user, pw, topic = parts
        self.save_mqtt_config(broker, port, user, pw, topic)
        try:
            from umqtt.simple import MQTTClient
            cid = self.device_id + "_" + str(int(time.time()))
            self.mqtt = MQTTClient(cid, broker, port=int(port), user=user, password=pw)
            self.mqtt.connect()
            self.notify("MQTT:OK")
        except Exception as e:
            self.mqtt = None
            self.notify("MQTT:ERR:" + str(e))

    def mqtt_disconnect(self):
        if self.mqtt:
            try:
                self.mqtt.disconnect()
            except:
                pass
            self.mqtt = None
        self.notify("MQTT:STOP")

    def mqtt_test(self):
        if not self.ensure_mqtt():
            self.notify("MQTT:TEST:ERR:nc")
            return
        try:
            import gc
            temp_c = round(_read_temp(), 1)
            gc.collect()
            freq = machine.freq() // 1000000
            mem_alloc = gc.mem_alloc()
            mem_free = gc.mem_free()
            self._publish_devinfo(temp_c, freq, mem_alloc, mem_free)
            if self.mqtt:
                self.notify("MQTT:TEST:OK")
            else:
                self.notify("MQTT:TEST:ERR:drop")
        except Exception as e:
            self.mqtt = None
            self.notify("MQTT:TEST:ERR:" + str(e)[:5])

    def report_mqtt(self):
        if self.mqtt:
            self.notify("MQTT:OK")
        else:
            self.notify("MQTT:STOP")
        self.report_mqtt_config()

    def report_mqtt_config(self):
        try:
            if "config.json" in os.listdir():
                with open("config.json") as f:
                    c = json.load(f)
                b = c.get("mqtt_broker", "")
                p = c.get("mqtt_port", "1883")
                u = c.get("mqtt_user", "")
                t = c.get("mqtt_topic", "")
                if b:
                    self.notify("MQTTCFG:" + f"{b},{p},{u},{t}")
        except:
            pass

    def save_mqtt_config(self, broker, port, user, pw, topic):
        try:
            c = {}
            if "config.json" in os.listdir():
                with open("config.json") as f:
                    c = json.load(f)
            c["mqtt_broker"] = broker
            c["mqtt_port"] = port
            c["mqtt_user"] = user
            c["mqtt_pw"] = pw
            c["mqtt_topic"] = topic
            with open("config.json", "w") as f:
                json.dump(c, f)
        except:
            pass

    def scan_wifi(self):
        self.notify("MSG:Scanning...")
        res = self.wlan.scan()
        ssids = sorted(res, key=lambda x: x[3], reverse=True)
        names = [s[0].decode() for s in ssids if s[0]][:5]
        self.notify("SSIDS:" + ",".join(names))

    def connect_wifi(self, ssid, pw):
        self.notify("MSG:Connecting...")
        self.wlan.disconnect()
        self.wlan.connect(ssid, pw)
        for i in range(15):
            time.sleep(1)
            if self.wlan.isconnected():
                ip = self.wlan.ifconfig()[0]
                self.notify("SUCCESS:" + ip)
                return
        self.notify("ERR:Timeout")

    def save_config(self, s, p):
        with open("config.json", "w") as f:
            json.dump({"ssid": s, "pw": p}, f)

    def load_and_connect(self):
        try:
            if "config.json" in os.listdir():
                with open("config.json") as f:
                    c = json.load(f)
                if c.get("ssid"):
                    self.wlan.connect(c["ssid"], c["pw"])
                    # 等待 WiFi 最多 20 秒
                    for _ in range(20):
                        time.sleep(1)
                        if self.wlan.isconnected():
                            break
                if self.wlan.isconnected() and c.get("mqtt_broker"):
                    self._auto_mqtt_connect(c)
        except:
            pass

    def _auto_mqtt_connect(self, c):
        try:
            from umqtt.simple import MQTTClient
            cid = c.get("device_id", "picow") + "_" + str(int(time.time()))
            self.mqtt = MQTTClient(
                cid, c["mqtt_broker"],
                port=int(c.get("mqtt_port", 1883)),
                user=c.get("mqtt_user", ""),
                password=c.get("mqtt_pw", "")
            )
            self.mqtt.connect()
        except:
            self.mqtt = None

    def ensure_mqtt(self):
        """若 MQTT 未連線且 WiFi 已就緒，自動嘗試重連一次"""
        if self.mqtt:
            return True
        if not self.wlan.isconnected():
            return False
        try:
            if "config.json" in os.listdir():
                with open("config.json") as f:
                    c = json.load(f)
                if c.get("mqtt_broker"):
                    self._auto_mqtt_connect(c)
                    return self.mqtt is not None
        except:
            pass
        return False

    def _advertise(self, interval_us=500000):
        try:
            p = advertising_payload(name=self.device_id, services=[_UART_UUID])
            self._ble.gap_advertise(interval_us, adv_data=p)
        except OSError:
            pass


ble = bluetooth.BLE()
DeviceManager(ble)
