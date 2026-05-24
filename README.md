# BLE WiFi Provisioner for Pico W (阿好伯技術分享)

這是一個專為 Raspberry Pi Pico W 設計的無線網路配置工具。透過 **Web Bluetooth API**，你不需要安裝任何 App，直接使用瀏覽器就能為你的 IoT 設備設定 WiFi。

## 💡 專案亮點
- **免 App 運作**：基於 Web Bluetooth 技術，開啟網頁即可連線硬體。
- **分段傳輸協定 (Chunking)**：克服 BLE MTU 限制，支援長 SSID 與複雜密碼傳輸，確保資料不截斷。
- **自動復歸**：連線資訊自動儲存於 `config.json`，設備重啟後會自動重連。
- **即時回饋**：網頁端可顯示硬體連線狀態（Connecting / Success / IP Address）。

## 🛠️ 硬體準備
- Raspberry Pi Pico W x1
- 已安裝 MicroPython 韌體
- `ble_advertising.py` (必須上傳至 Pico W)

## 📂 檔案結構
- `main.py`: Pico W 端的核心邏輯（包含 BLE 服務、分段緩衝與 WiFi 連線監控）。
- `index.html`: 管理端網頁（實作 Web Bluetooth 切片發送邏輯）。
- `config.json`: (自動產生) 儲存加密後的網路資訊。

## 🚀 快速開始

### 1. 燒錄硬體
1. 將 `main.py` 與 `ble_advertising.py` 透過 Thonny 存入 Pico W。
2. 執行後，板載 LED 會待命，藍牙廣播名稱為 `PicoW`。

### 2. 開啟網頁
1. 進入此專案的 GitHub Pages 連結（必須為 HTTPS 環境）。
2. 點擊 **"連接設備"** 並選擇 `PicoW`。
3. 點擊 **"掃描 WiFi"** 獲取周邊熱點。
4. 輸入密碼後點擊 **"設定並連線"**。

## 🔧 技術細節：分段傳輸 (Chunking)
由於 BLE 預設單次傳輸長度限制（約 20 bytes），本專案實作了簡單的手法：
- **發送端 (JS)**：將指令每 18 字元切割一次，並在末端附加 `END` 標記。
- **接收端 (MicroPython)**：利用 `cmd_buffer` 持續累加片段，直到辨識到結束符號才觸發連線邏輯。

---
## 🌐 即時演示 (Live Demo)

本專案已部署於 GitHub Pages，你可以直接開啟以下連結進行 WiFi 配置：
https://gtgrthrst.github.io/pico-w-ble-manager/
*(請使用 Chrome 或 Edge 瀏覽器以支援 Web Bluetooth)*
📱 iPhone / iOS 使用說明
由於 iOS 上的 Safari、Chrome 和 Firefox 目前皆「不支援」原生 Web Bluetooth API，iPhone 使用者必須透過特定的瀏覽器 App 才能與你的 Pico W 連線。
1. 下載專用瀏覽器
請至 App Store 下載以下其中一款支援藍牙功能的瀏覽器：
Bluefy (最推薦，免費且穩定)
WebBLE (付費，功能強大)

## 👤 關於作者
**阿好伯 (Ah-Bo-Bo)**
技術部落客 / 專業工程師 / 創客
> 專注於 Homelab、PVE、Docker 與 IoT 實作分享。
