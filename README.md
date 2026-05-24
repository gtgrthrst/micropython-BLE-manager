# micropython-BLE-manager

Raspberry Pi Pico W 管理工具，透過 **Web Bluetooth API** 在瀏覽器中直接操作硬體

**🔗 管理介面：https://gtgrthrst.github.io/micropython-BLE-manager/**

## 功能

- **WiFi 配置**：掃描熱點、輸入密碼一鍵連線，自動儲存至 `config.json`
- **MQTT 整合**：設定 Broker / 帳密 / 主題前綴，定期發布裝置資訊 JSON
- **裝置資訊儀表板**：即時顯示 CPU 溫度、頻率、記憶體、儲存及 SVG 火花圖
- **資料記錄**：每 N 秒寫入 `data.bin`，可匯出 CSV
- **裝置 ID**：自訂 BLE 廣播名稱與 MQTT Client ID

## 硬體需求

- Raspberry Pi Pico W + MicroPython
- `umqtt.simple` 安裝於 `/lib/umqtt/simple.mpy`

## 檔案結構

```
├── main.py              # Pico W 韌體（BLE、DataLogger、MQTT、WiFi）
├── ble_advertising.py   # BLE 廣播 payload 輔助
├── index.html           # Web BLE 管理介面（單一 HTML，無外部相依）
├── README.md
└── umqtt/
    └── simple.py        # MQTT 客戶端
```

裝置上自動產生：`/config.json`、`/data.bin`

## 快速開始

```bash
mpremote cp main.py :main.py
mpremote cp ble_advertising.py :ble_advertising.py
mpremote cp umqtt/simple.py :lib/umqtt/simple.mpy
mpremote reset
```

用 Chrome / Edge 開啟 `index.html` 或上方 GitHub Pages 連結。

> iOS 不支援 Web Bluetooth，請使用 [Bluefy](https://apps.apple.com/app/bluefy/id1492822055)。

## BLE 通訊協定

| 命令 | 說明 |
|---|---|
| `SCAN` | 掃描 WiFi |
| `W:<ssid>,<pw>` | 連線 WiFi |
| `WIFISTATUS` | 查詢 WiFi 狀態 |
| `DEVINFO` | 查詢裝置資訊（溫度、頻率、記憶體、ID） |
| `STATUS` | 查詢儲存狀態 |
| `MQTTSET:<broker>,<port>,<user>,<pw>,<topic>` | 設定並連線 MQTT |
| `MQTTTEST` | 發送測試訊息 |
| `SETDEVID:<id>` | 設定裝置 ID |
| `SETPERIOD:<sec>` | 設定記錄間隔（1–60 秒） |
| `CSV` | 匯出 CSV |
| `DELDATA` | 清除記錄 |
| `1` / `0` | LED ON / OFF |

## 授權

MIT License
