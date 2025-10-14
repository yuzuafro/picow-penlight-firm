"""
Raspberry Pi Pico W ペンライトコントローラー

Web Bluetooth APIを使用してフルカラーLEDを制御するプログラムです。
色選択モードと自動制御モード（3パターン）をサポートします。
"""

import bluetooth
import time
import machine
from machine import Pin
import neopixel
import ubinascii
import struct
import json

# グローバル設定
LED_PIN = 6  # NeoPixelの接続ピン
NUM_LEDS = 1  # LEDの数

class PenlightController:
    """
    ペンライトLED制御クラス

    NeoPixel互換LEDの制御と自動制御パターンの管理を行います。

    Attributes:
        np (neopixel.NeoPixel): NeoPixelオブジェクト
        num_leds (int): LED数
        current_color (tuple): 現在の色 (R, G, B)
        auto_mode (bool): 自動制御モードのON/OFF
        pattern_type (int): 自動制御のパターン番号 (1-3)
        pattern_colors (list): 自動制御で使用する色のリスト
        pattern_index (int): 現在のパターンインデックス
        last_pattern_update (int): 最後のパターン更新時刻 (ms)
    """

    def __init__(self, led_pin=6, num_leds=1):
        """
        PenlightControllerの初期化

        Args:
            led_pin (int): LEDのデータ線を接続するGPIOピン番号（デフォルト: 6）
            num_leds (int): 制御するLED数（デフォルト: 1）
        """
        self.np = neopixel.NeoPixel(machine.Pin(led_pin), num_leds)
        self.num_leds = num_leds
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
            (255, 192, 203) # ピンク
        ]
        self.pattern_index = 0
        self.last_pattern_update = time.ticks_ms()

    def set_color(self, r, g, b):
        """
        全LEDを指定色に設定

        Args:
            r (int): 赤色の輝度 (0-255)
            g (int): 緑色の輝度 (0-255)
            b (int): 青色の輝度 (0-255)
        """
        self.current_color = (r, g, b)
        for i in range(self.num_leds):
            self.np[i] = (r, g, b)
        self.np.write()

    def clear_leds(self):
        """
        全LEDを消灯

        すべてのLEDをRGB(0, 0, 0)に設定して消灯します。
        """
        self.set_color(0, 0, 0)

    def start_auto_mode(self, pattern_type=1):
        """
        自動制御モード開始

        指定されたパターンで自動的に色を変化させるモードを開始します。

        Args:
            pattern_type (int): パターン番号（1-3）
                1: 順次色変化
                2: 点滅しながら色変化
                3: 高速色変化
        """
        self.auto_mode = True
        self.pattern_type = pattern_type
        self.pattern_index = 0
        self.last_pattern_update = time.ticks_ms()

    def stop_auto_mode(self):
        """
        自動制御モード停止

        自動制御モードを停止し、LEDを消灯します。
        """
        self.auto_mode = False
        self.clear_leds()

    def update_auto_mode(self):
        """
        自動制御モードの更新処理

        メインループから定期的に呼び出され、自動制御モードが有効な場合に
        パターンに応じてLEDの色を更新します。約1秒間隔で色が変化します。
        """
        if not self.auto_mode:
            return

        current_time = time.ticks_ms()
        if time.ticks_diff(current_time, self.last_pattern_update) >= 1000:  # 1秒間隔
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
                # パターン3: 高速変化
                color = self.pattern_colors[self.pattern_index]
                self.set_color(color[0], color[1], color[2])
                self.pattern_index = (self.pattern_index + 1) % len(self.pattern_colors)

            self.last_pattern_update = current_time

class BluetoothService:
    """
    Bluetooth Low Energy (BLE) サービス管理クラス

    Web Bluetooth APIとの通信を管理し、ペンライトコントローラーへの
    コマンドと色情報の送受信を行います。

    Attributes:
        penlight (PenlightController): 制御対象のペンライトコントローラー
        ble (bluetooth.BLE): BLEオブジェクト
        SERVICE_UUID (bluetooth.UUID): BLEサービスのUUID
        COLOR_CHAR_UUID (bluetooth.UUID): 色制御用キャラクタリスティックのUUID
        CONTROL_CHAR_UUID (bluetooth.UUID): コマンド制御用キャラクタリスティックのUUID
        connections (set): 接続中のデバイスのハンドルセット
        is_connected (bool): 接続状態フラグ
        blink_state (bool): 待機時の点滅状態
        last_blink_time (int): 最後の点滅更新時刻 (ms)
    """

    def __init__(self, penlight_controller):
        """
        BluetoothServiceの初期化

        Args:
            penlight_controller (PenlightController): 制御対象のペンライトコントローラー
        """
        self.penlight = penlight_controller
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
        self.is_connected = False

        # 待機時の点滅用
        self.blink_state = False
        self.last_blink_time = time.ticks_ms()

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
            self.is_connected = True
            # 接続されたら点滅を止めて消灯
            self.penlight.clear_leds()
            print(f"Device connected: {ubinascii.hexlify(addr).decode()}")

        elif event == 2:  # _IRQ_CENTRAL_DISCONNECT
            conn_handle, addr_type, addr = data
            self.connections.discard(conn_handle)
            self.is_connected = len(self.connections) > 0
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

        デバイス名 "Penlight" でBLEアドバタイジングを開始し、
        他のデバイスから検出可能にします。
        """
        name = b'Penlight'
        adv_data = bytearray()
        adv_data.extend(struct.pack('BB', len(name) + 1, 0x09))
        adv_data.extend(name)

        self.ble.gap_advertise(100, adv_data, resp_data=None, connectable=True)
        print("Advertising as 'Penlight'")

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
                    self.penlight.stop_auto_mode()
                    self.penlight.set_color(r, g, b)
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
                "AUTO:1-3" - 自動制御開始（パターン1-3）
                "STOP" - 自動制御停止
                "CLEAR" - LED消灯
        """
        try:
            if command.startswith('AUTO:'):
                pattern_num = int(command.split(':')[1])
                self.penlight.start_auto_mode(pattern_num)
                print(f"Auto mode started with pattern {pattern_num}")

            elif command == 'STOP':
                self.penlight.stop_auto_mode()
                print("Auto mode stopped")

            elif command == 'CLEAR':
                self.penlight.stop_auto_mode()
                self.penlight.clear_leds()
                print("LEDs cleared")

        except Exception as e:
            print(f"Error handling command '{command}': {e}")

    def update_waiting_blink(self):
        """
        未接続時の青色点滅を更新

        Bluetooth未接続時に青色LEDを点滅させて待機状態を示します。
        点灯0.1秒 → 消灯4.9秒のパターンで繰り返します。

        Note:
            接続中または自動制御モード中は点滅しません。
            メインループから定期的に呼び出される必要があります。
        """
        if self.is_connected or self.penlight.auto_mode:
            # 接続中または自動制御モード中は点滅しない
            return

        current_time = time.ticks_ms()

        if self.blink_state:
            # 点灯中 → 0.1秒後に消灯
            if time.ticks_diff(current_time, self.last_blink_time) >= 100:
                self.penlight.clear_leds()  # 消灯
                self.blink_state = False
                self.last_blink_time = current_time
        else:
            # 消灯中 → 4.9秒後に点灯
            if time.ticks_diff(current_time, self.last_blink_time) >= 4900:
                self.penlight.set_color(0, 0, 255)  # 青色点灯
                self.blink_state = True
                self.last_blink_time = current_time

def main():
    """
    メインエントリーポイント

    ペンライトコントローラーとBluetoothサービスを初期化し、
    メインループを実行します。

    処理の流れ:
        1. LED初期化と起動テスト（赤→緑→青）
        2. Bluetoothサービス開始
        3. メインループ:
            - 未接続時の青色点滅更新
            - 自動制御モードの更新
        4. 終了時にLED消灯

    Raises:
        KeyboardInterrupt: Ctrl+Cで正常終了
    """
    print("Penlight Controller starting...")

    penlight = PenlightController(LED_PIN, NUM_LEDS)
    penlight.clear_leds()

    # 起動時のテスト点灯
    print("Testing LEDs...")
    penlight.set_color(255, 0, 0)  # 赤
    time.sleep(0.3)
    penlight.set_color(0, 255, 0)  # 緑
    time.sleep(0.3)
    penlight.set_color(0, 0, 255)  # 青
    time.sleep(0.3)
    penlight.clear_leds()

    # Bluetoothサービス開始
    bt_service = BluetoothService(penlight)

    print("Ready for connections!")
    print("LED will blink blue until connected...")

    # メインループ
    while True:
        try:
            # 未接続時の青色点滅を更新
            bt_service.update_waiting_blink()
            # 自動制御モードの更新
            penlight.update_auto_mode()
            time.sleep(0.1)  # CPU負荷を抑えつつタイミング精度を確保
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Main loop error: {e}")
            time.sleep(1)

    print("Shutting down...")
    penlight.clear_leds()

if __name__ == "__main__":
    main()