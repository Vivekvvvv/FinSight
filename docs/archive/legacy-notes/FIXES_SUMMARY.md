# 淇鎬荤粨

## 1. 鍓嶇鏁版嵁鑾峰彇鏄剧ず闂淇 鉁?
### 闂
鍓嶇鏄剧ず"鈿狅笍 鏃犳硶鑾峰彇鏁版嵁 (鏄剧ず妯℃嫙鏁版嵁)"锛屼絾鍚庣瀹為檯涓婂凡缁忔垚鍔熻幏鍙栦簡鐪熷疄鏁版嵁銆?
### 鍘熷洜
鍓嶇鏁版嵁瑙ｆ瀽閫昏緫鏈夎锛?- `apiClient.fetchKline` 杩斿洖鐨勬槸 `response.data`锛屽嵆鍚庣杩斿洖鐨勫畬鏁存暟鎹?- 鍓嶇浠ｇ爜閿欒鍦颁娇鐢ㄤ簡 `res.data.data.kline_data`锛屽簲璇ユ槸 `res.data.kline_data`

### 淇
- 鏇存柊浜?`frontend/src/components/StockChart.tsx` 鐨勬暟鎹В鏋愰€昏緫
- 娣诲姞浜嗚缁嗙殑鏃ュ織杈撳嚭锛屼究浜庤皟璇?- 鏇存柊浜?`frontend/src/types/index.ts` 涓殑 `KlineResponse` 鎺ュ彛锛屾坊鍔犱簡 `source`銆乣period`銆乣interval` 绛夊瓧娈?
### 娴嬭瘯
- 鍚庣鏃ュ織鏄剧ず锛歚[get_stock_historical_data] 鉁?yfinance 鎴愬姛鑾峰彇 250 鏉℃暟鎹?(鏉ユ簮: yfinance)`
- 鍓嶇鐜板湪搴旇鑳芥纭樉绀虹湡瀹炴暟鎹?
## 2. 榛樿妯″瀷閰嶇疆鏇存柊 鉁?
### 鏇存敼
- 灏嗛粯璁ゆā鍨嬩粠 `gemini-2.5-flash-preview-05-20` 鏇存柊涓?`gemini-2.5-flash` 鎴?`gemini-2.5-pro`
- 鏇存柊浜?`backend/config.py` 涓殑妯″瀷鍒楄〃椤哄簭锛屼紭鍏堜娇鐢ㄧǔ瀹氱増鏈?- 鏇存柊浜?`backend/langchain_agent.py` 涓殑妯″瀷閫夋嫨閫昏緫
- 鏇存柊浜?`backend/cli_app.py` 涓殑榛樿鍙傛暟

### 閰嶇疆閫昏緫
```python
# 浼樺厛閫夋嫨 gemini-2.5-flash 鎴?gemini-2.5-pro
preferred_models = ["gemini-2.5-flash", "gemini-2.5-pro"]
for preferred in preferred_models:
    if preferred in models:
        model = preferred
        break
```

## 3. 鏁版嵁鑾峰彇浼樺寲 鉁?
### 鏀硅繘
- 灏?yfinance 鎻愬崌涓轰紭鍏堢瓥鐣ワ紙绛栫暐 0锛?- 娣诲姞浜嗛噸璇曟満鍒跺拰閿欒澶勭悊
- 鏀寔鑲＄エ鍜屾寚鏁版暟鎹幏鍙?- 娴嬭瘯閫氳繃锛氭垚鍔熻幏鍙?AAPL 鍜?^IXIC 鐨勭湡瀹炴暟鎹?
## 涓嬩竴姝ワ細浠诲姟9 - 灞曠ずAgent鎬濊€冭繃绋?
闇€瑕佸疄鐜帮細
1. 鍦?API 鍝嶅簲涓寘鍚€濊€冭繃绋?2. 鍓嶇鏄剧ず鎬濊€冭繃绋嬶紙鍙睍寮€/鏀惰捣锛?3. 浣跨敤 LangChain 娴佸紡鐢熸垚锛堝鏋滃彲鑳斤級
