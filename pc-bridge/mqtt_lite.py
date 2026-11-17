"""Minimal MQTT 3.1.1 client over TLS: QoS 0 publish/subscribe with retained messages."""
import os, socket, ssl, struct, threading, time

BROKERS = [("broker.hivemq.com", 8883), ("broker.emqx.io", 8883), ("test.mosquitto.org", 8886)]


def _varint(n):
    out = bytearray()
    while True:
        b, n = n % 128, n // 128
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _str(s):
    b = s.encode() if isinstance(s, str) else s
    return struct.pack(">H", len(b)) + b


class MqttClient:
    def __init__(self, host, port, on_message=None, keepalive=60):
        self.host, self.port, self.keepalive = host, port, keepalive
        self.on_message = on_message
        self.sock = None
        self.wlock = threading.Lock()
        self.alive = False

    def connect(self, timeout=10):
        raw = socket.create_connection((self.host, self.port), timeout=timeout)
        self.sock = ssl.create_default_context().wrap_socket(raw, server_hostname=self.host)
        cid = "aps-" + os.urandom(6).hex()
        body = _str("MQTT") + bytes([4, 0x02]) + struct.pack(">H", self.keepalive) + _str(cid)
        self._send(0x10, body)
        ptype, data = self._read_packet()
        if ptype != 0x20 or data[1] != 0:
            raise ConnectionError(f"CONNACK refused: {data!r}")
        self.sock.settimeout(None)
        self.alive = True
        threading.Thread(target=self._reader, daemon=True).start()
        threading.Thread(target=self._pinger, daemon=True).start()

    def subscribe(self, topic):
        self._send(0x82, struct.pack(">H", 1) + _str(topic) + b"\x00")

    def publish(self, topic, payload, retain=False):
        self._send(0x30 | (1 if retain else 0), _str(topic) + payload)

    def close(self):
        self.alive = False
        try:
            self._send(0xE0, b"")
            self.sock.close()
        except Exception:
            pass

    def _send(self, header, body):
        with self.wlock:
            self.sock.sendall(bytes([header]) + _varint(len(body)) + body)

    def _recv_exact(self, n):
        buf = bytearray()
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("closed")
            buf += chunk
        return bytes(buf)

    def _read_packet(self):
        header = self._recv_exact(1)[0]
        mult, length = 1, 0
        while True:
            b = self._recv_exact(1)[0]
            length += (b & 0x7F) * mult
            mult *= 128
            if not b & 0x80:
                break
        return header & 0xF0, self._recv_exact(length)

    def _reader(self):
        try:
            while self.alive:
                ptype, data = self._read_packet()
                if ptype == 0x30 and self.on_message:
                    tlen = struct.unpack(">H", data[:2])[0]
                    self.on_message(data[2:2 + tlen].decode(), data[2 + tlen:])
        except Exception:
            pass
        self.alive = False

    def _pinger(self):
        while self.alive:
            time.sleep(self.keepalive / 2)
            try:
                self._send(0xC0, b"")
            except Exception:
                self.alive = False
