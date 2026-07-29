import json
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

LINE_BROADCAST_URL = "https://api.line.me/v2/bot/message/broadcast"
DATA_FILE = "data.json"
CONFIG_FILE = "line_config.json"
TOP_N = 5


def load_token():
    token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
    if token:
        return token

    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f).get("channel_access_token")

    return None


def build_message():
    with open(DATA_FILE, encoding="utf-8") as f:
        rows = json.load(f)

    today = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y/%m/%d")
    lines = [f"📊 台股盤後資訊 {today}", "", f"殖利率排行 Top {TOP_N}:"]

    for i, row in enumerate(rows[:TOP_N], start=1):
        lines.append(f"{i}. {row['代號']} {row['名稱']} {row['殖利率(%)']}%")

    return "\n".join(lines)


def broadcast(message: str, channel_access_token: str):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {channel_access_token}",
    }
    payload = {"messages": [{"type": "text", "text": message}]}

    response = requests.post(LINE_BROADCAST_URL, headers=headers, json=payload, timeout=15)

    if response.status_code != 200:
        print(f"❌ 推播失敗 ({response.status_code}): {response.text}")
        sys.exit(1)

    print("✅ 已成功推播盤後資訊給所有好友")


if __name__ == "__main__":
    token = load_token()
    if not token:
        print(f"❌ 找不到 token。請設定環境變數 LINE_CHANNEL_ACCESS_TOKEN,或建立 {CONFIG_FILE}")
        sys.exit(1)

    msg = build_message()
    print("--- 推播內容預覽 ---")
    print(msg)
    print("--------------------")
    broadcast(msg, token)
