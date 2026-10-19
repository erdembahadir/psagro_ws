#!/usr/bin/env python3
import re

import rclpy
from rclpy.node import Node
from std_msgs.msg import String, ColorRGBA
from geometry_msgs.msg import Point, Quaternion
from visualization_msgs.msg import Marker, InteractiveMarker, InteractiveMarkerControl
from visualization_msgs.msg import InteractiveMarkerFeedback
from interactive_markers import InteractiveMarkerServer, MenuHandler


class PumpInteractiveNode(Node):

    def __init__(self):
        super().__init__('pump_interactive')

        # ── Parametreler ──────────────────────────────────────────────────────
        # pump_positions: düz liste [x0,y0,z0, x1,y1,z1, x2,y2,z2, x3,y3,z3]
        # base_link.STL bounding box (y ekseninde 4 eşit bölme, z=max+%8 offset):
        #   bbox  x:[-0.713, 0.287]  y:[-2.676, -1.126]  z:[-0.015, 0.710]
        #   segment_len = 1.550/4 = 0.3875 m  →  scale = 0.3875 * 0.35 ≈ 0.136
        self.declare_parameter('pump_positions', [
            -0.213, -2.482,  0.768,
            -0.213, -2.095,  0.768,
            -0.213, -1.707,  0.768,
            -0.213, -1.320,  0.768,
        ])
        self.declare_parameter('marker_scale', 0.136)
        self.declare_parameter('frame_id', 'base_link')

        pos_flat = list(
            self.get_parameter('pump_positions').get_parameter_value().double_array_value
        )
        scale = self.get_parameter('marker_scale').get_parameter_value().double_value
        frame = self.get_parameter('frame_id').get_parameter_value().string_value

        self._scale = scale
        self._frame = frame
        self._positions = [
            (pos_flat[i * 3], pos_flat[i * 3 + 1], pos_flat[i * 3 + 2])
            for i in range(4)
        ]

        # ── İç durum ──────────────────────────────────────────────────────────
        self._pump_state = [False, False, False, False]

        # ── ROS arayüzleri ────────────────────────────────────────────────────
        self._cmd_pub = self.create_publisher(String, '/pump_command', 10)
        self.create_subscription(String, '/pump_status', self._on_status, 10)
        self.create_timer(2.0, self._status_tick)

        # ── Interactive marker sunucusu ────────────────────────────────────────
        self._server = InteractiveMarkerServer(self, 'pump_markers')
        self._menu = MenuHandler()

        # Menü girişleri (handle'ları sakla; callback pompa numarasını feedback'ten alır)
        self._entry_on  = self._menu.insert('Ac (ON)',         callback=self._on_menu)
        self._entry_off = self._menu.insert('Kapat (OFF)',     callback=self._on_menu)
        self._entry_run = self._menu.insert('5 sn calistir',  callback=self._on_menu)

        for i in range(4):
            self._make_marker(i)
            self._menu.apply(self._server, f'pump_{i}')

        self._server.applyChanges()
        self.get_logger().info('pump_interactive hazir — 4 marker olusturuldu')

    # ── Durum mesajı ──────────────────────────────────────────────────────────

    def _on_status(self, msg: String):
        data = msg.data.strip()
        old = self._pump_state[:]

        if data == 'ACK:ALL_ON':
            self._pump_state = [True] * 4

        elif data == 'ACK:ALL_OFF':
            self._pump_state = [False] * 4

        elif data.startswith('STATUS,'):
            # "STATUS,a,b,c,d"  — 1/ON/true = açık
            parts = data.split(',')
            if len(parts) == 5:
                for i in range(4):
                    self._pump_state[i] = parts[i + 1].strip().upper() in ('1', 'ON', 'TRUE')

        else:
            n = self._parse_pump_num(data)
            if n is not None:
                if '_OFF' in data or data.startswith('OFF:'):
                    self._pump_state[n] = False
                else:
                    # _ON veya _RUN_* → açık
                    self._pump_state[n] = True

        if self._pump_state != old:
            self._update_all_markers()

    def _parse_pump_num(self, data: str):
        # P1..P4 → 0-indexed
        m = re.search(r'P(\d+)', data)
        if m:
            n = int(m.group(1)) - 1
            if 0 <= n < 4:
                return n
        return None

    # ── Periyodik STATUS isteği ───────────────────────────────────────────────

    def _status_tick(self):
        self._cmd_pub.publish(String(data='STATUS'))

    # ── Marker oluşturma ──────────────────────────────────────────────────────

    def _build_cube(self, idx: int) -> Marker:
        cube = Marker()
        cube.type = Marker.CUBE
        cube.scale.x = self._scale
        cube.scale.y = self._scale
        cube.scale.z = self._scale
        cube.color = self._state_color(self._pump_state[idx])
        return cube

    def _make_marker(self, idx: int):
        im = InteractiveMarker()
        im.header.frame_id = self._frame
        im.name = f'pump_{idx}'
        im.description = f'Pompa {idx + 1}'
        # InteractiveMarker.scale handle görsel boyutunu etkiler; küp boyutu ayrı
        im.scale = self._scale * 3.0

        x, y, z = self._positions[idx]
        im.pose.position = Point(x=x, y=y, z=z)
        im.pose.orientation = Quaternion(w=1.0)

        ctrl = InteractiveMarkerControl()
        ctrl.interaction_mode = InteractiveMarkerControl.MENU
        ctrl.always_visible = True
        ctrl.name = 'menu_ctrl'
        ctrl.markers.append(self._build_cube(idx))
        im.controls.append(ctrl)

        self._server.insert(im, feedback_callback=self._on_feedback)

    # ── Güncelleme ────────────────────────────────────────────────────────────

    def _update_all_markers(self):
        for i in range(4):
            self._make_marker(i)          # rengi güncellenmiş marker'ı yeniden ekle
            self._menu.reApply(self._server)
        self._server.applyChanges()
        states = ['ACIk' if s else 'KAPALI' for s in self._pump_state]
        self.get_logger().info(f'Marker guncellendi: {states}')

    # ── Feedback ──────────────────────────────────────────────────────────────

    def _on_feedback(self, feedback: InteractiveMarkerFeedback):
        # Genel tıklama feedback'i; menü seçimi _on_menu'ye gider
        pass

    def _on_menu(self, feedback: InteractiveMarkerFeedback):
        name = feedback.marker_name          # "pump_0" … "pump_3"
        idx = int(name.split('_')[1])        # 0-indexed dahili
        pump_num = idx + 1                   # 1-indexed protokol: P1..P4 (P0 olmaz)
        assert 1 <= pump_num <= 4, f'Beklenmedik pompa indeksi: {pump_num}'

        eid = feedback.menu_entry_id
        if eid == self._entry_on:
            cmd = f'P{pump_num}_ON'
        elif eid == self._entry_off:
            cmd = f'P{pump_num}_OFF'
        elif eid == self._entry_run:
            cmd = f'P{pump_num}_RUN_5000'
        else:
            return

        self._cmd_pub.publish(String(data=cmd))
        self.get_logger().info(f'Komut gonderildi: {cmd}')

    # ── Yardımcı ──────────────────────────────────────────────────────────────

    @staticmethod
    def _state_color(on: bool) -> ColorRGBA:
        if on:
            return ColorRGBA(r=0.0, g=0.85, b=0.15, a=0.9)
        return ColorRGBA(r=0.85, g=0.05, b=0.05, a=0.9)


def main(args=None):
    rclpy.init(args=args)
    node = PumpInteractiveNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
