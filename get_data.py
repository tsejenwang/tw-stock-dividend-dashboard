import pandas as pd
import requests
import json

def fetch_twse_data():
    # 這是證交所 Open Data 提供的個股殖利率資料 API
    # 它可以取得最新一天的完整數據
    # 注意:原本這裡用的 BWIBHT_ALL 端點已經失效(會回傳 404 的 HTML 頁面而不是 JSON),
    # 已實測確認正確端點是 BWIBBU_ALL,回傳欄位是 Date/Code/Name/PEratio/DividendYield/PBratio。
    url = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL"
    
    print("正在從證交所開放資料介面抓取最新排名...")
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        
        # 檢查是否還是回傳 HTML
        if response.text.startswith("<!DOCTYPE"):
            print("❌ 依然被阻擋。這可能是因為您的 IP 請求過於頻繁。")
            print("建議：請稍等 5 分鐘後再試，或更換網路環境。")
            return

        # 直接讀取 JSON 陣列
        data = response.json()
        
        # 轉換成 Pandas 處理
        df = pd.DataFrame(data)
        
        # 轉換欄位名稱(BWIBBU_ALL 的殖利率欄位叫 'DividendYield',不是 'YieldRatio')
        df['DividendYield'] = pd.to_numeric(df['DividendYield'], errors='coerce')

        # 排序前 50 名
        top_50 = df.sort_values(by='DividendYield', ascending=False).head(50)

        # 將結果存成 index.html 可以讀取的格式
        # 為了配合你的網頁，我們把欄位改名
        result = top_50.rename(columns={
            'Code': '代號',
            'Name': '名稱',
            'DividendYield': '殖利率(%)'
        })
        
        result.to_json('data.json', orient='records', force_ascii=False)
        print(f"✅ 成功！已抓取 {len(result)} 筆最新資料並存至 data.json")

    except Exception as e:
        print(f"💥 發生非預期錯誤: {e}")

if __name__ == "__main__":
    fetch_twse_data()