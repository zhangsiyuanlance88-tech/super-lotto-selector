# -*- coding: utf-8 -*-
"""GitHub Actions 用：自动拉取体彩最新开奖，更新 lotto_data.js
纯标准库，无第三方依赖。失败时保持旧数据不覆盖。
"""
import json
import os
import re
import sys
import time
import urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE, 'lotto_data.js')
API_URL = ('https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry'
           '?gameNo=85&provinceId=0&pageSize=100&isVerify=1&pageNo=1')
API_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.lottery.gov.cn/',
    'Accept': 'application/json, text/javascript, */*; q=0.01',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'X-Requested-With': 'XMLHttpRequest',
}


def load_records():
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, encoding='utf-8') as f:
        text = f.read()
    m = re.search(r'window\.LOTTO_DATA\s*=\s*(\{.*?\});', text, re.S)
    if not m:
        return []
    return json.loads(m.group(1)).get('records', [])


def fetch_api():
    last_err = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(API_URL, headers=API_HEADERS)
            with urllib.request.urlopen(req, timeout=20) as resp:
                body = resp.read().decode('utf-8')
            raw = json.loads(body)
            items = raw.get('value', {}).get('list', [])
            records = []
            for item in items:
                parts = item.get('lotteryDrawResult', '').split()
                if len(parts) >= 7:
                    records.append({
                        'period': item.get('lotteryDrawNum', ''),
                        'front': [int(x) for x in parts[:5]],
                        'back': [int(x) for x in parts[5:7]],
                        'draw_date': item.get('lotteryDrawTime', '') or item.get('lotteryDrawDate', ''),
                    })
            if records:
                return records
        except Exception as e:
            last_err = e
            if attempt < 2:
                time.sleep(2)
    print('[警告] 官方接口失败:', last_err)
    return None


def fetch_500():
    """备用数据源：500.com 大乐透历史页（HTML 表格），校验严格，解析失败则放弃"""
    url = 'https://datachart.500.com/dlt/history/newinc/history.php?limit=100&sort=0'
    headers = dict(API_HEADERS)
    headers['Referer'] = 'https://datachart.500.com/dlt/history/history.shtml'
    headers['Accept-Encoding'] = 'identity'  # 关闭 gzip，避免压缩内容无法解析
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            html = resp.read().decode('gbk', errors='ignore')
    except Exception as e:
        print('[警告] 500.com 失败:', e)
        return None
    records = []
    for m in re.finditer(r'<tr[^>]*class="t_tr1"[^>]*>(.*?)</tr>', html, re.S):
        tds = re.findall(r'<td[^>]*>(.*?)</td>', m.group(1), re.S)
        tds = [re.sub(r'<[^>]+>', '', t).strip() for t in tds]
        if len(tds) < 8:
            continue
        period = tds[0]
        nums = [int(t) for t in tds[1:8] if t.isdigit()]
        if len(nums) == 7 and re.fullmatch(r'\d{5}', period) and all(1 <= n <= 35 for n in nums[:5]) and all(1 <= n <= 12 for n in nums[5:]):
            records.append({'period': period, 'front': nums[:5], 'back': nums[5:], 'draw_date': ''})
    if records:
        records.sort(key=lambda r: r['period'], reverse=True)
        print('[备用源] 500.com 拉到 %d 期' % len(records))
        return records
    print('[警告] 500.com 解析结果为空')
    return None


def main():
    fetched = fetch_api()
    if not fetched:
        print('官方源失败，尝试备用源…')
        fetched = fetch_500()
    if not fetched:
        print('没有拉到数据，保持现有数据不变')
        sys.exit(1)

    # 合并去重（新数据覆盖同 period 旧数据）
    merged = {r['period']: r for r in load_records()}
    for r in fetched:
        merged[r['period']] = r
    records = sorted(merged.values(), key=lambda r: r['period'], reverse=True)

    old_total = len(load_records()) if os.path.exists(DATA_FILE) else 0
    added = len(records) - old_total
    if added <= 0:
        print('数据已是最新，无需更新 (共 %d 期，最新 %s)' % (len(records), records[0]['period']))
        sys.exit(0)

    payload = {'updated': time.strftime('%Y-%m-%dT%H:%M:%S'), 'records': records}
    js = 'window.LOTTO_DATA = ' + json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + ';\n'
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        f.write(js)
    print('更新成功: +%d 期，共 %d 期，最新 %s' % (added, len(records), records[0]['period']))


if __name__ == '__main__':
    main()
