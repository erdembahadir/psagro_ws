#!/usr/bin/env python3
"""PSAGRO akış + iklim monitörü.

Abonelikler:
  /flow          std_msgs/String  "FLOW,<n>,<pulses>,<Lpm>"
  /climate       std_msgs/String  "CLIMATE,<t>,<h>"  |  "CLIMATE,ERR"
  /pump_status   std_msgs/String  durum güncelleme

Yayın:
  /pump_command  std_msgs/String  buton komutları (P1_ON … ALL_OFF  P1_RUN_<ms>)

Yapı: rclpy spin threadi ayrı; Tkinter mainloop ana thread'de; ~200 ms tazeleme.
"""

import threading
import time
import tkinter as tk
from tkinter import font as tkfont

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


# ── Renk sabitleri ────────────────────────────────────────────────────────────
BG         = '#1e1e2e'
PANEL_BG   = '#2a2a3e'
ACCENT     = '#89b4fa'
GREEN      = '#a6e3a1'
RED        = '#f38ba8'
YELLOW     = '#f9e2af'
TEXT       = '#cdd6f4'
SUBTEXT    = '#7f849c'
TEMP_COLOR = '#fab387'
HUM_COLOR  = '#89dceb'


class FlowMonitorNode(Node):
    def __init__(self):
        super().__init__('flow_monitor')

        # ── Per-sensör kalibrasyon sabitleri (darbe/litre) ────────────────────
        self.ppl = [5880, 5880]  # index 0 → Sensör 1, index 1 → Sensör 2

        # ── Paylaşımlı veri (thread-safe: GIL yeterli, atomik assign) ─────────
        self.flow_data  = {1: {'pulses': 0, 'lpm': 0.0},
                           2: {'pulses': 0, 'lpm': 0.0}}
        self._prev      = {1: (0, None), 2: (0, None)}  # (pulses, monotonic_ts)
        self.pump_state = [False] * 4
        self.temp: float | None = None
        self.hum:  float | None = None

        # ── Abonelikler ───────────────────────────────────────────────────────
        self.create_subscription(String, '/flow',        self._on_flow,    10)
        self.create_subscription(String, '/climate',     self._on_climate, 10)
        self.create_subscription(String, '/pump_status', self._on_status,  10)

        # ── Yayıncı ──────────────────────────────────────────────────────────
        self._cmd_pub = self.create_publisher(String, '/pump_command', 10)

    # ── Callbacks ─────────────────────────────────────────────────────────────

    def _on_flow(self, msg: String):
        # "FLOW,<n>,<pulses>,<lpm>"  — lpm Arduino'dan gelir, kendi ppl ile yeniden hesaplarız
        parts = msg.data.split(',')
        if len(parts) != 4:
            return
        try:
            n      = int(parts[1])
            pulses = int(parts[2])
        except ValueError:
            return
        if n not in self.flow_data:
            return

        ppl = self.ppl[n - 1]
        now = time.monotonic()
        prev_p, prev_t = self._prev[n]

        if prev_t is not None and ppl > 0:
            delta_p     = pulses - prev_p
            delta_t_min = (now - prev_t) / 60.0
            lpm = (delta_p / ppl) / delta_t_min if delta_t_min > 0 else 0.0
            lpm = max(0.0, lpm)
        else:
            lpm = 0.0

        self._prev[n] = (pulses, now)
        self.flow_data[n] = {'pulses': pulses, 'lpm': lpm}

    def _on_climate(self, msg: String):
        parts = msg.data.split(',')
        if len(parts) == 3 and parts[1] != 'ERR':
            try:
                self.temp = float(parts[1])
                self.hum  = float(parts[2])
            except ValueError:
                pass

    def _on_status(self, msg: String):
        data = msg.data.strip()
        if data.startswith('STATUS,'):
            parts = data.split(',')
            if len(parts) == 5:
                for i in range(4):
                    self.pump_state[i] = parts[i + 1].strip() == '1'
        elif data.startswith('ACK:P') and '_ON' in data:
            n = self._parse_pump(data)
            if n is not None:
                self.pump_state[n] = True
        elif data.startswith('ACK:P') and '_OFF' in data:
            n = self._parse_pump(data)
            if n is not None:
                self.pump_state[n] = False
        elif data.startswith('ACK:P') and '_RUN_' in data:
            n = self._parse_pump(data)
            if n is not None:
                self.pump_state[n] = True
        elif data.startswith('OFF:P'):
            n = self._parse_pump(data)
            if n is not None:
                self.pump_state[n] = False
        elif data == 'ACK:ALL_ON':
            self.pump_state = [True] * 4
        elif data == 'ACK:ALL_OFF':
            self.pump_state = [False] * 4

    @staticmethod
    def _parse_pump(data: str):
        import re
        m = re.search(r'P(\d+)', data)
        if m:
            n = int(m.group(1)) - 1
            if 0 <= n < 4:
                return n
        return None

    def send_cmd(self, cmd: str):
        self._cmd_pub.publish(String(data=cmd))
        self.get_logger().info(f'-> {cmd}')


# ── GUI ───────────────────────────────────────────────────────────────────────

class FlowMonitorGUI:
    REFRESH_MS = 200

    def __init__(self, root: tk.Tk, node: FlowMonitorNode):
        self.root = root
        self.node = node

        root.title('PSAGRO Monitör')
        root.configure(bg=BG)
        root.resizable(False, False)

        big      = tkfont.Font(family='DejaVu Sans', size=36, weight='bold')
        med      = tkfont.Font(family='DejaVu Sans', size=16, weight='bold')
        small    = tkfont.Font(family='DejaVu Sans', size=11)
        lbl_font = tkfont.Font(family='DejaVu Sans', size=10)
        tiny     = tkfont.Font(family='DejaVu Sans', size=9)

        # ── Başlık ───────────────────────────────────────────────────────────
        tk.Label(root, text='PSAGRO Sulama Sistemi',
                 bg=BG, fg=ACCENT,
                 font=tkfont.Font(family='DejaVu Sans', size=14, weight='bold')
                 ).pack(pady=(12, 4))

        # ── Ortam paneli ─────────────────────────────────────────────────────
        climate_frame = tk.LabelFrame(root, text=' Ortam ',
                                      bg=PANEL_BG, fg=ACCENT,
                                      font=lbl_font, bd=2, relief='groove')
        climate_frame.pack(fill='x', padx=14, pady=(4, 6))

        inner = tk.Frame(climate_frame, bg=PANEL_BG)
        inner.pack(pady=8)

        t_col = tk.Frame(inner, bg=PANEL_BG)
        t_col.grid(row=0, column=0, padx=30)
        tk.Label(t_col, text='Sıcaklık', bg=PANEL_BG, fg=SUBTEXT,
                 font=lbl_font).pack()
        self._temp_var = tk.StringVar(value='—')
        tk.Label(t_col, textvariable=self._temp_var,
                 bg=PANEL_BG, fg=TEMP_COLOR, font=big, width=5,
                 anchor='e').pack()
        tk.Label(t_col, text='°C', bg=PANEL_BG, fg=TEMP_COLOR, font=med).pack()

        h_col = tk.Frame(inner, bg=PANEL_BG)
        h_col.grid(row=0, column=1, padx=30)
        tk.Label(h_col, text='Nem', bg=PANEL_BG, fg=SUBTEXT,
                 font=lbl_font).pack()
        self._hum_var = tk.StringVar(value='—')
        tk.Label(h_col, textvariable=self._hum_var,
                 bg=PANEL_BG, fg=HUM_COLOR, font=big, width=5,
                 anchor='e').pack()
        tk.Label(h_col, text='%', bg=PANEL_BG, fg=HUM_COLOR, font=med).pack()

        # ── Akış panelleri ───────────────────────────────────────────────────
        flow_outer = tk.LabelFrame(root, text=' Akış Sensörleri ',
                                   bg=PANEL_BG, fg=ACCENT,
                                   font=lbl_font, bd=2, relief='groove')
        flow_outer.pack(fill='x', padx=14, pady=(0, 6))

        self._flow_lpm  = {}
        self._flow_vol  = {}
        self._flow_puls = {}
        self._ppl_vars  = {}  # ppl Entry StringVar'ları

        for idx, (n, sensor_label) in enumerate([(1, 'Sensör 1 (Pompa 1)'),
                                                  (2, 'Sensör 2 (Pompa 2)')]):
            col = tk.Frame(flow_outer, bg=PANEL_BG)
            col.grid(row=0, column=idx, padx=20, pady=8)

            tk.Label(col, text=sensor_label, bg=PANEL_BG, fg=SUBTEXT,
                     font=lbl_font).pack()

            lpm_var = tk.StringVar(value='0.00 L/dk')
            tk.Label(col, textvariable=lpm_var,
                     bg=PANEL_BG, fg=GREEN, font=med, width=13).pack()

            vol_var = tk.StringVar(value='0.000 L')
            tk.Label(col, textvariable=vol_var,
                     bg=PANEL_BG, fg=TEXT, font=small, width=12).pack()

            puls_var = tk.StringVar(value='0 darbe')
            tk.Label(col, textvariable=puls_var,
                     bg=PANEL_BG, fg=SUBTEXT, font=tiny).pack()

            self._flow_lpm[n]  = lpm_var
            self._flow_vol[n]  = vol_var
            self._flow_puls[n] = puls_var

            # ── PPL düzenleme satırı ──────────────────────────────────────
            ppl_row = tk.Frame(col, bg=PANEL_BG)
            ppl_row.pack(pady=(5, 2))
            tk.Label(ppl_row, text='PPL (darbe/L):', bg=PANEL_BG, fg=SUBTEXT,
                     font=tiny).pack(side='left')
            ppl_var = tk.StringVar(value=str(self.node.ppl[n - 1]))
            self._ppl_vars[n] = ppl_var
            ppl_entry = tk.Entry(ppl_row, textvariable=ppl_var,
                                  width=7, bg='#313244', fg=TEXT,
                                  insertbackground=TEXT, font=tiny, relief='flat')
            ppl_entry.pack(side='left', padx=(4, 0))

            def _apply_ppl(event=None, sensor=n, var=ppl_var):
                try:
                    val = int(float(var.get()))
                    if val > 0:
                        self.node.ppl[sensor - 1] = val
                        var.set(str(val))
                except ValueError:
                    var.set(str(self.node.ppl[sensor - 1]))

            ppl_entry.bind('<Return>',   _apply_ppl)
            ppl_entry.bind('<FocusOut>', _apply_ppl)

            # ── "1L'ye göre kalibre et" butonu ───────────────────────────
            tk.Button(
                col, text="1L'ye göre kalibre et",
                bg='#313244', fg=YELLOW, activebackground='#45475a',
                font=tiny, bd=0, pady=3,
                command=lambda sn=n: self._calibrate_1L(sn)
            ).pack(pady=(2, 0))

        # ── Pompa kontrol paneli ──────────────────────────────────────────────
        pump_frame = tk.LabelFrame(root, text=' Pompa Kontrol ',
                                   bg=PANEL_BG, fg=ACCENT,
                                   font=lbl_font, bd=2, relief='groove')
        pump_frame.pack(fill='x', padx=14, pady=(0, 6))

        self._pump_btns = []
        self._dur_vars  = []

        btn_row = tk.Frame(pump_frame, bg=PANEL_BG)
        btn_row.pack(pady=6)

        for i in range(4):
            col = tk.Frame(btn_row, bg=PANEL_BG)
            col.pack(side='left', padx=8)

            state_var = tk.StringVar(value='KAPALI')
            state_lbl = tk.Label(col, textvariable=state_var,
                                  bg=PANEL_BG, fg=RED, font=small, width=7)
            state_lbl.pack()

            pump_num = i + 1

            tk.Button(
                col, text=f'P{pump_num} AÇ',
                bg='#313244', fg=GREEN, activebackground='#45475a',
                font=small, width=8, bd=0, pady=4,
                command=lambda n=pump_num: self.node.send_cmd(f'P{n}_ON')
            ).pack(pady=(2, 1))

            tk.Button(
                col, text=f'P{pump_num} KAPA',
                bg='#313244', fg=RED, activebackground='#45475a',
                font=small, width=8, bd=0, pady=4,
                command=lambda n=pump_num: self.node.send_cmd(f'P{n}_OFF')
            ).pack()

            # ── Süre girişi (saniye, ondalık) + ÇALIŞTIR butonu ───────────
            dur_var = tk.StringVar(value='5.0')
            self._dur_vars.append(dur_var)

            dur_row = tk.Frame(col, bg=PANEL_BG)
            dur_row.pack(pady=(4, 1))
            tk.Label(dur_row, text='sn:', bg=PANEL_BG, fg=SUBTEXT,
                     font=tiny).pack(side='left')
            tk.Entry(dur_row, textvariable=dur_var,
                     width=6, bg='#313244', fg=TEXT,
                     insertbackground=TEXT, font=tiny, relief='flat'
                     ).pack(side='left', padx=(3, 0))

            tk.Button(
                col, text=f'P{pump_num} ÇALIŞTIR',
                bg='#313244', fg=YELLOW, activebackground='#45475a',
                font=tiny, width=10, bd=0, pady=3,
                command=lambda n=pump_num, dv=dur_var: self._run_pump(n, dv)
            ).pack(pady=(0, 2))

            self._pump_btns.append((state_var, state_lbl))

        # ALL OFF butonu
        all_row = tk.Frame(pump_frame, bg=PANEL_BG)
        all_row.pack(pady=(2, 8))
        tk.Button(all_row, text='TÜM POMPALAR KAPAT',
                  bg='#45475a', fg=RED, activebackground='#585b70',
                  font=tkfont.Font(family='DejaVu Sans', size=11, weight='bold'),
                  bd=0, pady=6, padx=20,
                  command=lambda: self.node.send_cmd('ALL_OFF')
                  ).pack()

        # ── İlk güncelleme ───────────────────────────────────────────────────
        self._refresh()

    # ── Kalibrasyon ───────────────────────────────────────────────────────────

    def _calibrate_1L(self, sensor: int):
        """Tam 1L toplandıktan sonra basılır; o anki toplam pulse → ppl."""
        pulses = self.node.flow_data[sensor]['pulses']
        if pulses > 0:
            self.node.ppl[sensor - 1] = pulses
            self._ppl_vars[sensor].set(str(pulses))

    # ── Pompa çalıştır ────────────────────────────────────────────────────────

    def _run_pump(self, pump_num: int, dur_var: tk.StringVar):
        try:
            seconds = float(dur_var.get())
            if seconds <= 0:
                return
            ms = round(seconds * 1000)
            self.node.send_cmd(f'P{pump_num}_RUN_{ms}')
        except ValueError:
            pass

    # ── Periyodik tazeleme ────────────────────────────────────────────────────

    def _refresh(self):
        # İklim
        if self.node.temp is not None:
            self._temp_var.set(f'{self.node.temp:.1f}')
        if self.node.hum is not None:
            self._hum_var.set(f'{self.node.hum:.1f}')

        # Akış — her sensör kendi ppl'i ile hesaplanır
        for n in (1, 2):
            data   = self.node.flow_data[n]
            pulses = data['pulses']
            lpm    = data['lpm']
            ppl    = self.node.ppl[n - 1]
            total_L = pulses / ppl if ppl > 0 else 0.0

            self._flow_lpm[n].set(f'{lpm:.2f} L/dk')
            self._flow_vol[n].set(f'{total_L:.3f} L')
            self._flow_puls[n].set(f'{pulses} darbe')

        # Pompa durumları
        for i, (state_var, state_lbl) in enumerate(self._pump_btns):
            on = self.node.pump_state[i]
            state_var.set('AÇIK' if on else 'KAPALI')
            state_lbl.config(fg=GREEN if on else RED)

        self.root.after(self.REFRESH_MS, self._refresh)


# ── main ──────────────────────────────────────────────────────────────────────

def main(args=None):
    rclpy.init(args=args)
    node = FlowMonitorNode()

    spin_thread = threading.Thread(target=rclpy.spin, args=(node,), daemon=True)
    spin_thread.start()

    root = tk.Tk()
    FlowMonitorGUI(root, node)
    try:
        root.mainloop()
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
