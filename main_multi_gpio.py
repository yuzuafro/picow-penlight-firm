"""
Raspberry Pi Pico W カラーライトコントローラー（複数GPIO対応版）

複数のGPIOピンに接続された複数のLEDストリップを同時制御します。
Web Bluetooth APIを使用してフルカラーLEDを制御するプログラムです。
色選択モードと自動制御モード（4パターン）をサポートします。
"""

import bluetooth
import time
import machine
import neopixel
import ubinascii
import struct

# 複数のLEDストリップ設定
LED_STRIPS = [
    {'pin': 6, 'num_leds': 8},   # GPIO6に8個
    {'pin': 7, 'num_leds': 8},   # GPIO7に8個
]

# グローバル設定
DEVICE_ID = 1  # デバイス識別番号（1-99）複数台使用時は各デバイスで変更してください

class MultiStripColorlightController:
    """
    複数のLEDストリップ制御クラス

    複数のGPIOピンに接続された複数のNeoPixel互換LEDストリップを
    同時制御し、自動制御パターンの管理を行います。

    Attributes:
        strips (list): LEDストリップ情報のリスト
            各要素は {'np': NeoPixel, 'num_leds': int, 'pin': int} の辞書
        current_color (tuple): 現在の色 (R, G, B)
        auto_mode (bool): 自動制御モードのON/OFF
        pattern_type (int): 自動制御のパターン番号 (1-4)
        pattern_colors (list): 自動制御パターン1・2で使用する色のリスト（7色）
        gradient_colors (list): パターン3用の虹色グラデーション色のリスト（96段階）
        pattern_index (int): 現在のパターンインデックス
        last_pattern_update (int): 最後のパターン更新時刻 (ms)
    """

    def __init__(self, led_strips):
        """
        MultiStripColorlightControllerの初期化

        Args:
            led_strips (list): LEDストリップ設定のリスト
                例: [{'pin': 6, 'num_leds': 8}, {'pin': 7, 'num_leds': 4}, ...]
        """
        self.strips = []
        for config in led_strips:
            strip = {
                'np': neopixel.NeoPixel(machine.Pin(config['pin']), config['num_leds']),
                'num_leds': config['num_leds'],
                'pin': config['pin']
            }
            self.strips.append(strip)
            print(f"Initialized LED strip on GPIO{config['pin']} with {config['num_leds']} LEDs")

        self.current_color = (0, 0, 0)
        self.auto_mode = False
        self.pattern_type = 1
        self.pattern_colors = [
            (255, 0, 0),    # 赤
            (255, 165, 0),  # 橙
            (255, 255, 0),  # 黄
            (0, 255, 0),    # 緑
            (0, 0, 255),    # 青
            (128, 0, 128),  # 紫
            (255, 20, 147)  # ピンク (Deep Pink)
        ]
        # パターン3用のシームレスなグラデーション色（96段階の虹色）
        self.gradient_colors = self._generate_rainbow_gradient(96)
        self.pattern_index = 0
        self.last_pattern_update = time.ticks_ms()

    def _generate_rainbow_gradient(self, steps):
        """
        虹色のグラデーションを生成

        Args:
            steps (int): グラデーションのステップ数

        Returns:
            list: RGB色のタプルのリスト
        """
        colors = []
        for i in range(steps):
            # HSVカラーの色相(Hue)を0-360度で変化させる
            hue = (i * 360) // steps
            r, g, b = self._hsv_to_rgb(hue, 100, 100)
            colors.append((r, g, b))
        return colors

    def _hsv_to_rgb(self, h, s, v):
        """
        HSV色空間からRGB色空間に変換

        Args:
            h (int): 色相 (0-360)
            s (int): 彩度 (0-100)
            v (int): 明度 (0-100)

        Returns:
            tuple: (R, G, B) それぞれ0-255
        """
        s = s / 100.0
        v = v / 100.0
        c = v * s
        x = c * (1 - abs(((h / 60.0) % 2) - 1))
        m = v - c

        if 0 <= h < 60:
            r, g, b = c, x, 0
        elif 60 <= h < 120:
            r, g, b = x, c, 0
        elif 120 <= h < 180:
            r, g, b = 0, c, x
        elif 180 <= h < 240:
            r, g, b = 0, x, c
        elif 240 <= h < 300:
            r, g, b = x, 0, c
        else:
            r, g, b = c, 0, x

        return (int((r + m) * 255), int((g + m) * 255), int((b + m) * 255))

    def set_color(self, r, g, b):
        """
        全ストリップの全LEDを指定色に設定

        Args:
            r (int): 赤色の輝度 (0-255)
            g (int): 緑色の輝度 (0-255)
            b (int): 青色の輝度 (0-255)
        """
        self.current_color = (r, g, b)
        for strip in self.strips:
            for i in range(strip['num_leds']):
                strip['np'][i] = (r, g, b)
            strip['np'].write()

    def set_strip_color(self, strip_index, r, g, b):
        """
        特定のストリップのみ色を設定

        Args:
            strip_index (int): ストリップのインデックス (0始まり)
            r (int): 赤色の輝度 (0-255)
            g (int): 緑色の輝度 (0-255)
            b (int): 青色の輝度 (0-255)
        """
        if 0 <= strip_index < len(self.strips):
            strip = self.strips[strip_index]
            for i in range(strip['num_leds']):
                strip['np'][i] = (r, g, b)
            strip['np'].write()

    def clear_leds(self):
        """
        全LEDを消灯

        すべてのストリップのすべてのLEDをRGB(0, 0, 0)に設定して消灯します。
        """
        self.set_color(0, 0, 0)

    def start_auto_mode(self, pattern_type=1):
        """
        自動制御モード開始

        指定されたパターンで自動的に色を変化させるモードを開始します。

        Args:
            pattern_type (int): パターン番号（1-4）
                1: 順次色変化（7色を1秒ごとに切り替え）
                2: 点滅パターン（7色を1秒ごとに点灯・消灯を繰り返す）
                3: シームレスな虹色グラデーション（96段階を0.5秒ごとに切り替え）
                4: 交互点灯（複数ストリップが交互に点灯、1秒ごとに切り替え）
        """
        self.auto_mode = True
        self.pattern_type = pattern_type
        self.pattern_index = 0
        self.last_pattern_update = time.ticks_ms()

    def stop_auto_mode(self):
        """
        自動制御モード停止

        自動制御モードを停止し、すべてのLEDを消灯します。
        """
        self.auto_mode = False
        self.clear_leds()

    def update_auto_mode(self):
        """
        自動制御モードの更新処理

        メインループから定期的に呼び出され、自動制御モードが有効な場合に
        パターンに応じてLEDの色を更新します。

        更新間隔:
            - パターン1: 1秒間隔で7色を順次切り替え
            - パターン2: 1秒間隔で7色の点灯・消灯を繰り返し
            - パターン3: 0.5秒間隔で96段階の虹色グラデーションを表示
            - パターン4: 1秒間隔でストリップを交互に点灯
        """
        if not self.auto_mode:
            return

        current_time = time.ticks_ms()
        # パターン3は0.5秒間隔、それ以外は1秒間隔
        interval = 500 if self.pattern_type == 3 else 1000

        if time.ticks_diff(current_time, self.last_pattern_update) >= interval:
            if self.pattern_type == 1:
                # パターン1: 順次色変化
                color = self.pattern_colors[self.pattern_index]
                self.set_color(color[0], color[1], color[2])
                self.pattern_index = (self.pattern_index + 1) % len(self.pattern_colors)
            elif self.pattern_type == 2:
                # パターン2: 点滅
                if self.pattern_index % 2 == 0:
                    color = self.pattern_colors[(self.pattern_index // 2) % len(self.pattern_colors)]
                    self.set_color(color[0], color[1], color[2])
                else:
                    self.clear_leds()
                self.pattern_index += 1
            elif self.pattern_type == 3:
                # パターン3: シームレスな虹色グラデーション
                color = self.gradient_colors[self.pattern_index]
                self.set_color(color[0], color[1], color[2])
                self.pattern_index = (self.pattern_index + 1) % len(self.gradient_colors)
            elif self.pattern_type == 4:
                # パターン4: 交互点灯（複数ストリップ用）
                for i, strip in enumerate(self.strips):
                    if (self.pattern_index + i) % 2 == 0:
                        color = self.pattern_colors[(self.pattern_index // 2) % len(self.pattern_colors)]
                        self.set_strip_color(i, color[0], color[1], color[2])
                    else:
                        self.set_strip_color(i, 0, 0, 0)
                self.pattern_index += 1

            self.last_pattern_update = current_time

class BluetoothService:
    """
    Bluetooth Low Energy (BLE) サービス管理クラス

    Web Bluetooth APIとの通信を管理し、カラーライトコントローラーへの
    コマンドと色情報の送受信を行います。

    Attributes:
        colorlight (MultiStripColorlightController): 制御対象のカラーライトコントローラー
        device_id (int): デバイス識別番号（1-99）
        ble (bluetooth.BLE): BLEオブジェクト
        SERVICE_UUID (bluetooth.UUID): BLEサービスのUUID
        COLOR_CHAR_UUID (bluetooth.UUID): 色制御用キャラクタリスティックのUUID
        CONTROL_CHAR_UUID (bluetooth.UUID): コマンド制御用キャラクタリスティックのUUID
        color_handle (int): 色制御キャラクタリスティックのハンドル
        control_handle (int): コマンド制御キャラクタリスティックのハンドル
        connections (set): 接続中のデバイスのハンドルセット
    """

    def __init__(self, colorlight_controller, device_id=1):
        """
        BluetoothServiceの初期化

        Args:
            colorlight_controller (MultiStripColorlightController): 制御対象のカラーライトコントローラー
            device_id (int): デバイス識別番号（1-99）
        """
        self.colorlight = colorlight_controller
        self.device_id = device_id
        self.ble = bluetooth.BLE()
        self.ble.active(True)
        self.ble.irq(self._irq)

        # UUIDs for the service and characteristics
        self.SERVICE_UUID = bluetooth.UUID('12345678-1234-1234-1234-123456789abc')
        self.COLOR_CHAR_UUID = bluetooth.UUID('12345678-1234-1234-1234-123456789abd')
        self.CONTROL_CHAR_UUID = bluetooth.UUID('12345678-1234-1234-1234-123456789abe')

        # Register services
        self._register_services()
        self._advertise()

        self.connections = set()

    def _irq(self, event, data):
        """
        BLE割り込みハンドラ

        BLEイベント（接続、切断、データ書き込み）を処理します。

        Args:
            event (int): イベントタイプ
                1: _IRQ_CENTRAL_CONNECT (接続)
                2: _IRQ_CENTRAL_DISCONNECT (切断)
                3: _IRQ_GATTS_WRITE (書き込み)
            data (tuple): イベントデータ
        """
        if event == 1:  # _IRQ_CENTRAL_CONNECT
            conn_handle, addr_type, addr = data
            self.connections.add(conn_handle)
            print(f"Device connected: {ubinascii.hexlify(addr).decode()}")

        elif event == 2:  # _IRQ_CENTRAL_DISCONNECT
            conn_handle, addr_type, addr = data
            self.connections.discard(conn_handle)
            print(f"Device disconnected: {ubinascii.hexlify(addr).decode()}")
            self._advertise()

        elif event == 3:  # _IRQ_GATTS_WRITE
            conn_handle, value_handle = data
            value = self.ble.gatts_read(value_handle)
            self._handle_write(value_handle, value)

    def _register_services(self):
        """
        BLEサービスとキャラクタリスティックの登録

        色制御用とコマンド制御用の2つのキャラクタリスティックを持つ
        BLEサービスを登録します。
        """
        # Color characteristic (RGB values)
        color_char = (
            self.COLOR_CHAR_UUID,
            bluetooth.FLAG_WRITE | bluetooth.FLAG_READ,
        )

        # Control characteristic (commands)
        control_char = (
            self.CONTROL_CHAR_UUID,
            bluetooth.FLAG_WRITE | bluetooth.FLAG_READ,
        )

        service = (self.SERVICE_UUID, (color_char, control_char))
        services = (service,)

        ((self.color_handle, self.control_handle),) = self.ble.gatts_register_services(services)

    def _advertise(self):
        """
        BLEアドバタイジングの開始

        デバイス名 "Colorlight-{device_id}" でBLEアドバタイジングを開始し、
        他のデバイスから検出可能にします。
        """
        name = f'Colorlight-{self.device_id}'.encode('utf-8')
        adv_data = bytearray()
        adv_data.extend(struct.pack('BB', len(name) + 1, 0x09))
        adv_data.extend(name)

        self.ble.gap_advertise(100, adv_data, resp_data=None, connectable=True)
        print(f"Advertising as 'Colorlight-{self.device_id}'")

    def _handle_write(self, value_handle, value):
        """
        BLE書き込みリクエストの処理

        色制御またはコマンド制御のキャラクタリスティックへの
        書き込みを処理します。

        Args:
            value_handle (int): 書き込み先のキャラクタリスティックハンドル
            value (bytes): 書き込まれたデータ
        """
        try:
            if value_handle == self.color_handle:
                # Color data: expects 3 bytes (R, G, B)
                if len(value) >= 3:
                    r, g, b = value[0], value[1], value[2]
                    self.colorlight.stop_auto_mode()
                    self.colorlight.set_color(r, g, b)
                    print(f"Color set to RGB({r}, {g}, {b})")

            elif value_handle == self.control_handle:
                # Control commands
                command = value.decode('utf-8').strip()
                self._handle_command(command)

        except Exception as e:
            print(f"Error handling write: {e}")

    def _handle_command(self, command):
        """
        制御コマンドの処理

        Webアプリから送信されたコマンド文字列を解析して実行します。

        Args:
            command (str): コマンド文字列
                "AUTO:1" - パターン1: 順次色変化（7色を1秒ごとに切り替え）
                "AUTO:2" - パターン2: 点滅パターン（7色を1秒ごとに点灯・消灯）
                "AUTO:3" - パターン3: 虹色グラデーション（96段階を0.5秒ごと）
                "AUTO:4" - パターン4: 交互点灯（ストリップを交互に点灯）
                "STOP" - 自動制御モード停止
                "CLEAR" - LED消灯
                "MUSIC:{brightness}" - 音楽モード（明るさ0-255）
                    ※現在未使用。音楽連動はWebアプリ側で音声解析し、
                    　COLOR_CHARへRGB値を直接送信する方式で実装済み。
        """
        try:
            if command.startswith('AUTO:'):
                pattern_num = int(command.split(':')[1])
                self.colorlight.start_auto_mode(pattern_num)
                print(f"Auto mode started with pattern {pattern_num}")

            elif command == 'STOP':
                self.colorlight.stop_auto_mode()
                print("Auto mode stopped")

            elif command == 'CLEAR':
                self.colorlight.stop_auto_mode()
                self.colorlight.clear_leds()
                print("LEDs cleared")

            elif command.startswith('MUSIC:'):
                # 音楽モード: 明るさ値を取得
                brightness = int(command.split(':')[1])
                brightness = max(0, min(255, brightness))  # 0-255に制限
                # 現在の色を保持しながら明るさを調整
                # 音楽モード時は自動制御を停止
                self.colorlight.stop_auto_mode()
                print(f"Music mode: brightness {brightness}")

        except Exception as e:
            print(f"Error handling command '{command}': {e}")

def main():
    """
    メインエントリーポイント

    複数ストリップのカラーライトコントローラーとBluetoothサービスを初期化し、
    メインループを実行します。

    処理の流れ:
        1. LED初期化と起動テスト（全ストリップ同時→個別）
        2. Bluetoothサービス開始
        3. メインループ: 自動制御モードの更新
        4. 終了時にLED消灯

    Raises:
        KeyboardInterrupt: Ctrl+Cで正常終了
    """
    print("Multi-Strip Colorlight Controller starting...")
    print(f"Configured {len(LED_STRIPS)} LED strips:")
    for i, config in enumerate(LED_STRIPS):
        print(f"  Strip {i}: GPIO{config['pin']} with {config['num_leds']} LEDs")

    colorlight = MultiStripColorlightController(LED_STRIPS)
    colorlight.clear_leds()

    # 起動時のテスト点灯（全ストリップ同時）
    print("\nTesting all strips together...")
    colorlight.set_color(255, 0, 0)  # 赤
    time.sleep(0.5)
    colorlight.set_color(0, 255, 0)  # 緑
    time.sleep(0.5)
    colorlight.set_color(0, 0, 255)  # 青
    time.sleep(0.5)

    # 各ストリップ個別テスト
    print("Testing each strip individually...")
    for i in range(len(colorlight.strips)):
        print(f"  Testing strip {i} on GPIO{colorlight.strips[i]['pin']}")
        colorlight.clear_leds()
        colorlight.set_strip_color(i, 255, 255, 255)  # 白
        time.sleep(0.5)

    colorlight.clear_leds()

    # Bluetoothサービス開始
    bt_service = BluetoothService(colorlight, DEVICE_ID)

    print("\nReady for connections!")
    print(f"Device ID: {DEVICE_ID}")

    # メインループ
    while True:
        try:
            colorlight.update_auto_mode()
            time.sleep(0.1)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Main loop error: {e}")
            time.sleep(1)

    print("Shutting down...")
    colorlight.clear_leds()

if __name__ == "__main__":
    main()
