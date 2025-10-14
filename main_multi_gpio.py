import bluetooth
import time
import machine
from machine import Pin
import neopixel
import ubinascii
import struct
import json

# 複数のLEDストリップ設定
LED_STRIPS = [
    {'pin': 6, 'num_leds': 8},   # GPIO6に8個
    {'pin': 7, 'num_leds': 8},   # GPIO7に8個
]

class MultiStripPenlightController:
    def __init__(self, led_strips):
        """
        複数のLEDストリップを制御
        led_strips: [{'pin': 6, 'num_leds': 8}, {'pin': 7, 'num_leds': 4}, ...]
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
            (255, 192, 203) # ピンク
        ]
        self.pattern_index = 0
        self.last_pattern_update = time.ticks_ms()

    def set_color(self, r, g, b):
        """全ストリップの全LEDを指定色に設定"""
        self.current_color = (r, g, b)
        for strip in self.strips:
            for i in range(strip['num_leds']):
                strip['np'][i] = (r, g, b)
            strip['np'].write()

    def set_strip_color(self, strip_index, r, g, b):
        """特定のストリップのみ色を設定"""
        if 0 <= strip_index < len(self.strips):
            strip = self.strips[strip_index]
            for i in range(strip['num_leds']):
                strip['np'][i] = (r, g, b)
            strip['np'].write()

    def clear_leds(self):
        """全LEDを消灯"""
        self.set_color(0, 0, 0)

    def start_auto_mode(self, pattern_type=1):
        """自動制御モード開始"""
        self.auto_mode = True
        self.pattern_type = pattern_type
        self.pattern_index = 0
        self.last_pattern_update = time.ticks_ms()

    def stop_auto_mode(self):
        """自動制御モード停止"""
        self.auto_mode = False
        self.clear_leds()

    def update_auto_mode(self):
        """自動制御モードの更新処理"""
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
    def __init__(self, penlight_controller):
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

    def _irq(self, event, data):
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
        name = b'Penlight'
        adv_data = bytearray()
        adv_data.extend(struct.pack('BB', len(name) + 1, 0x09))
        adv_data.extend(name)

        self.ble.gap_advertise(100, adv_data, resp_data=None, connectable=True)
        print("Advertising as 'Penlight'")

    def _handle_write(self, value_handle, value):
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
        """コマンド処理"""
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

def main():
    print("Multi-Strip Penlight Controller starting...")
    print(f"Configured {len(LED_STRIPS)} LED strips:")
    for i, config in enumerate(LED_STRIPS):
        print(f"  Strip {i}: GPIO{config['pin']} with {config['num_leds']} LEDs")

    penlight = MultiStripPenlightController(LED_STRIPS)
    penlight.clear_leds()

    # 起動時のテスト点灯（全ストリップ同時）
    print("\nTesting all strips together...")
    penlight.set_color(255, 0, 0)  # 赤
    time.sleep(0.5)
    penlight.set_color(0, 255, 0)  # 緑
    time.sleep(0.5)
    penlight.set_color(0, 0, 255)  # 青
    time.sleep(0.5)

    # 各ストリップ個別テスト
    print("Testing each strip individually...")
    for i in range(len(penlight.strips)):
        print(f"  Testing strip {i} on GPIO{penlight.strips[i]['pin']}")
        penlight.clear_leds()
        penlight.set_strip_color(i, 255, 255, 255)  # 白
        time.sleep(0.5)

    penlight.clear_leds()

    # Bluetoothサービス開始
    bt_service = BluetoothService(penlight)

    print("\nReady for connections!")

    # メインループ
    while True:
        try:
            penlight.update_auto_mode()
            time.sleep(0.1)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Main loop error: {e}")
            time.sleep(1)

    print("Shutting down...")
    penlight.clear_leds()

if __name__ == "__main__":
    main()
