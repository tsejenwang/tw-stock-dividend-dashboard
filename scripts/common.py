# -*- coding: utf-8 -*-
"""
共用工具:HTTP 重試機制、路徑設定。
重試邏輯移植自 c:\\stock\\stock_widget.py 的 http_get()。
"""
import os
import time

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
}

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")


def ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def data_path(filename: str) -> str:
    ensure_data_dir()
    return os.path.join(DATA_DIR, filename)


def http_get(session: requests.Session, url: str, **kwargs):
    """帶重試機制的 GET,遇連線錯誤或 5xx 會等一下重試,最多 3 次。"""
    last_err = None
    resp = None
    for attempt in range(3):
        try:
            resp = session.get(url, **kwargs)
        except requests.exceptions.RequestException as e:
            last_err = e
            resp = None
        if resp is not None and resp.status_code < 500:
            return resp
        if attempt < 2:
            time.sleep(2.0 * (attempt + 1))
    if resp is not None:
        return resp
    raise last_err


def new_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s
