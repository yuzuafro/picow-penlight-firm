"""
LED動作テスト用スクリプト
このファイルをThonnyで実行してLEDの動作を確認してください
"""

import machine
import neopixel
import time

# 設定
LED_PIN = 6
NUM_LEDS = 8

print("LED テスト開始")
print(f"LED_PIN: GPIO{LED_PIN}")
print(f"LED数: {NUM_LEDS}")

try:
    # NeoPixelの初期化
    np = neopixel.NeoPixel(machine.Pin(LED_PIN), NUM_LEDS)
    print("NeoPixel初期化成功")

    # テスト1: 赤（全LED）
    print("\nテスト1: 赤 (255, 0, 0) - 全LED")
    for i in range(NUM_LEDS):
        np[i] = (255, 0, 0)
    np.write()
    time.sleep(2)

    # テスト2: 緑（全LED）
    print("テスト2: 緑 (0, 255, 0) - 全LED")
    for i in range(NUM_LEDS):
        np[i] = (0, 255, 0)
    np.write()
    time.sleep(2)

    # テスト3: 青（全LED）
    print("テスト3: 青 (0, 0, 255) - 全LED")
    for i in range(NUM_LEDS):
        np[i] = (0, 0, 255)
    np.write()
    time.sleep(2)

    # テスト4: 白（全LED）
    print("テスト4: 白 (255, 255, 255) - 全LED")
    for i in range(NUM_LEDS):
        np[i] = (255, 255, 255)
    np.write()
    time.sleep(2)

    # テスト5: 低輝度白（配線確認用・全LED）
    print("テスト5: 低輝度白 (10, 10, 10) - 全LED")
    for i in range(NUM_LEDS):
        np[i] = (10, 10, 10)
    np.write()
    time.sleep(2)

    # テスト6: 1個ずつ点灯（個別テスト）
    print("テスト6: 1個ずつ点灯")
    for i in range(NUM_LEDS):
        # 全消灯
        for j in range(NUM_LEDS):
            np[j] = (0, 0, 0)
        # i番目だけ点灯
        np[i] = (255, 0, 255)  # マゼンタ
        np.write()
        print(f"  LED {i} 点灯")
        time.sleep(0.5)

    # 消灯
    print("消灯")
    for i in range(NUM_LEDS):
        np[i] = (0, 0, 0)
    np.write()

    print("\nテスト完了！")
    print("\nLEDが光らない場合:")
    print("1. 配線を確認してください")
    print("   - Data線がGPIO6に接続されているか")
    print("   - VCCが5V (VBUS)に接続されているか")
    print("   - GNDがGNDに接続されているか")
    print("2. LEDの極性を確認してください")
    print("3. 電源供給が十分か確認してください")
    print("4. LEDの型番がWS2812B互換か確認してください")

except Exception as e:
    print(f"\nエラー発生: {e}")
    print("\n考えられる原因:")
    print("- GPIO6が使用できない")
    print("- NeoPixelライブラリの問題")
    print("- ハードウェアの問題")
