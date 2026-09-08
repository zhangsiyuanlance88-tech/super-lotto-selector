"""超级大乐透智能选号 - 云端服务 (Flask)"""

import json
import os
import urllib.request
import urllib.error
from datetime import datetime
from flask import Flask, jsonify, request, send_file, send_from_directory, Response

app = Flask(__name__, static_folder=".", static_url_path="")

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "lotto_db.json")
API_URL = "https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry?gameNo=85&provinceId=0&pageSize=100&isVerify=1&pageNo=1"
API_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.lottery.gov.cn/",
}


def load_db():
    if os.path.exists(DB_PATH):
        try:
            with open(DB_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"version": 1, "updated": "", "records": []}


def save_db(db):
    db["updated"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, separators=(",", ":"))


def merge_records(db, new_records):
    existing = {r["period"] for r in db["records"]}
    added = 0
    for r in new_records:
        if r["period"] not in existing:
            db["records"].insert(0, r)
            existing.add(r["period"])
            added += 1
    if added > 0:
        db["records"].sort(key=lambda x: int(x["period"]), reverse=True)
        save_db(db)
    return added


def fetch_from_api():
    try:
        req = urllib.request.Request(API_URL, headers=API_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
        if not raw.get("success"):
            return []
        records = []
        for item in raw["value"]["list"]:
            parts = item["lotteryDrawResult"].split()
            if len(parts) >= 7:
                records.append({
                    "period": item["lotteryDrawNum"],
                    "front": [int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])],
                    "back": [int(parts[5]), int(parts[6])],
                    "draw_date": item.get("lotteryDrawDate", ""),
                })
        return records
    except Exception as e:
        print(f"Fetch error: {e}")
        return []


# ========== 静态文件 ==========
@app.route("/")
def index():
    return send_file("index.html")


# ========== API 路由 ==========
@app.route("/api/data")
def api_data():
    db = load_db()
    return jsonify({"count": len(db["records"]), "updated": db["updated"], "records": db["records"]})


@app.route("/api/stats")
def api_stats():
    db = load_db()
    latest = db["records"][0]["period"] if db["records"] else ""
    oldest = db["records"][-1]["period"] if db["records"] else ""
    return jsonify({
        "total": len(db["records"]),
        "latest": latest,
        "oldest": oldest,
        "updated": db["updated"],
    })


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    db = load_db()
    new_records = fetch_from_api()
    if not new_records:
        return jsonify({"ok": False, "error": "API request failed", "added": 0})
    added = merge_records(db, new_records)
    db = load_db()
    latest = db["records"][0]["period"] if db["records"] else ""
    return jsonify({
        "ok": True,
        "added": added,
        "total": len(db["records"]),
        "latest": latest,
        "updated": db["updated"],
    })


@app.route("/api/export")
def api_export():
    db = load_db()
    lines = ["period,draw_date,front_1,front_2,front_3,front_4,front_5,back_1,back_2"]
    for r in db["records"]:
        date = r.get("draw_date", "")
        f = r["front"]
        b = r["back"]
        lines.append(f"{r['period']},{date},{f[0]},{f[1]},{f[2]},{f[3]},{f[4]},{b[0]},{b[1]}")
    csv_content = "\n".join(lines)
    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=dlt_all.csv"},
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8765))
    app.run(host="0.0.0.0", port=port, debug=False)