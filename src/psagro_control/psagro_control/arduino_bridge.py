#!/usr/bin/env python3
import threading
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import serial


class ArduinoBridge(Node):
    _RECONNECT_DELAY = 2.0

    def __init__(self):
        super().__init__('arduino_bridge')
        self.declare_parameter('port', '/dev/ttyUSB0')
        self.declare_parameter('baud', 115200)
        self._port = self.get_parameter('port').get_parameter_value().string_value
        self._baud = self.get_parameter('baud').get_parameter_value().integer_value

        self._lock = threading.Lock()
        self._ser: serial.Serial | None = None

        self.pub = self.create_publisher(String, '/pump_status', 10)
        self.flow_pub = self.create_publisher(String, '/flow', 10)
        self.climate_pub = self.create_publisher(String, '/climate', 10)
        self.create_subscription(String, '/pump_command', self.on_command, 10)

        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    # ── Bağlantı yönetimi ────────────────────────────────────────────────────

    def _open_port(self) -> bool:
        try:
            ser = serial.Serial(self._port, self._baud, timeout=0.1)
        except (serial.SerialException, OSError) as e:
            self.get_logger().warn(
                f'Baglanti hatasi [{self._port}]: {e} '
                f'— {self._RECONNECT_DELAY:.0f}s sonra tekrar deneniyor'
            )
            return False
        with self._lock:
            self._ser = ser
        self.get_logger().info(f'Arduino baglandi: {self._port} @ {self._baud}')
        return True

    def _close_port(self):
        with self._lock:
            ser, self._ser = self._ser, None
        if ser is not None:
            try:
                ser.close()
            except Exception:
                pass

    # ── Okuma döngüsü (yeniden bağlanma destekli) ────────────────────────────

    def _read_loop(self):
        while rclpy.ok():
            with self._lock:
                ser = self._ser

            if ser is None:
                # Bağlantı yok: dene; başarısızsa bekle; ikisinde de döngü başa döner.
                if not self._open_port():
                    time.sleep(self._RECONNECT_DELAY)
                continue

            try:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
            except (serial.SerialException, OSError) as e:
                self.get_logger().error(
                    f'Okuma hatasi: {e} — port kapatiliyor, {self._RECONNECT_DELAY:.0f}s sonra yeniden baglaniliyor'
                )
                self._close_port()
                time.sleep(self._RECONNECT_DELAY)
                continue

            if line:
                self.get_logger().info(f'<- {line}')
                if line.startswith('FLOW,'):
                    self.flow_pub.publish(String(data=line))
                elif line.startswith('CLIMATE,'):
                    self.climate_pub.publish(String(data=line))
                else:
                    self.pub.publish(String(data=line))

    # ── Komut yazma ──────────────────────────────────────────────────────────

    def on_command(self, msg: String):
        cmd = msg.data.strip()
        if not cmd:
            return

        with self._lock:
            ser = self._ser

        if ser is None or not ser.is_open:
            self.get_logger().warn(f'Port kapali — komut atildi: {cmd}')
            return

        try:
            with self._lock:
                ser.write((cmd + '\n').encode('utf-8'))
            self.get_logger().info(f'-> {cmd}')
        except (serial.SerialException, OSError) as e:
            self.get_logger().error(f'Yazma hatasi: {e}')
            self._close_port()

    # ── Kapat ────────────────────────────────────────────────────────────────

    def safe_shutdown(self):
        with self._lock:
            ser = self._ser
        if ser is not None and ser.is_open:
            try:
                ser.write(b'ALL_OFF\n')
                ser.close()
            except Exception:
                pass


def main(args=None):
    rclpy.init(args=args)
    node = ArduinoBridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.safe_shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
