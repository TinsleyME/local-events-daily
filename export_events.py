#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
local-events-daily 独立导出脚本
双击运行，将 data/ 与 dims/ 导出为 JSON 到 exported-json/ 目录。

输出格式对齐 stamp-map eventsFallback 最新 JSON 规范（与 stamp-map-admin 的
export_all_events_json / export_event_city_json 完全一致）：
  单城市 <CODE>.json: { "version", "updatedAt", "data": { "events": [], "venues": [] } }
  合并 ALL.json:      { "version", "updatedAt", "data": { "events": [], "venues": [] } }

约定：
  - version:   字符串版本号 "1.0.0"（固定）
  - updatedAt: 毫秒时间戳整数（int(time.time() * 1000)）
  - data.events / data.venues 均为数组
  - 文件名使用大写城市代码（如 GZ.json），与 stamp-map eventsFallback 城市目录 / 远程 REMOTE 规范一致
"""
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DIMS_DIR = os.path.join(BASE_DIR, "dims")
OUT_DIR = os.path.join(BASE_DIR, "exported-json")

# 与 stamp-map 导出对齐的版本号
_EXPORT_VERSION = "1.0.0"


def _read_js_global(path: str, var: str) -> Any:
    """读取 window.XXX = {...} 或 window.XXX = [...] 格式的 JS 文件，返回解析后的对象。

    依赖行尾的 `;?$` 锚点，确保贪婪回溯到最后一个 `}`/`]`，从而完整捕获嵌套对象/数组。
    """
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = re.search(rf"window\.{re.escape(var)}\s*=\s*(\{{.*?\}}|\[.*?\])\s*;?\s*$", text, re.S)
    if not m:
        raise ValueError(f"{path} 中未找到 window.{var}")
    return json.loads(m.group(1))


def _load_city_codes() -> List[str]:
    """从 data/ 目录推断城市代码（小写后缀，如 gz）。"""
    codes = []
    for name in os.listdir(DATA_DIR):
        if name.startswith("data_") and name.endswith(".js"):
            codes.append(name[5:-3])
    return sorted(codes)


def _load_venues(code: str) -> List[Dict[str, Any]]:
    path = os.path.join(DIMS_DIR, f"venues_{code}.js")
    if not os.path.exists(path):
        return []
    return _read_js_global(path, f"APP_VENUES_{code.upper()}")


def _load_city_data(code: str) -> Dict[str, Any]:
    path = os.path.join(DATA_DIR, f"data_{code}.js")
    return _read_js_global(path, "APP_DATA")


def _now_ms() -> int:
    return int(time.time() * 1000)


def _write_json_uppercase(path: str, obj: Dict[str, Any]) -> None:
    """写入 JSON 文件。

    Windows 文件系统大小写不敏感，若目标路径已存在同名（仅大小写不同）的旧文件，
    直接 open 写入会沿用旧目录项的小写名称。这里先删除旧项再创建，确保大写城市码
    文件名（如 GZ.json）在 Windows 上也正确落盘，与 stamp-map 远程 REMOTE 规范一致。
    """
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def export_city(code: str) -> Optional[Dict[str, Any]]:
    """导出单个城市为最新 JSON 结构：{ version, updatedAt, data: { events, venues } }。"""
    try:
        data = _load_city_data(code)
        venues = _load_venues(code)
    except Exception as e:
        print(f"[WARN] {code}: {e}")
        return None

    events = data.get("events", []) if isinstance(data, dict) else []
    return {
        "version": _EXPORT_VERSION,
        "updatedAt": _now_ms(),
        "data": {
            "events": events,
            "venues": venues,
        },
    }


def export_all() -> Dict[str, Any]:
    """导出全量数据：逐城市 JSON（大写文件名）+ 合并扁平 ALL.json，均为最新格式。"""
    os.makedirs(OUT_DIR, exist_ok=True)
    codes = _load_city_codes()

    per_city: Dict[str, Any] = {}
    all_events: List[Dict[str, Any]] = []
    all_venues: List[Dict[str, Any]] = []

    for code in codes:
        obj = export_city(code)
        if obj is None:
            continue
        per_city[code] = obj
        all_events.extend(obj["data"]["events"])
        all_venues.extend(obj["data"]["venues"])

        # 文件名使用大写城市代码，与 stamp-map eventsFallback / 远程 REMOTE 规范一致
        out_path = os.path.join(OUT_DIR, f"{code.upper()}.json")
        _write_json_uppercase(out_path, obj)
        print(f"  {code.upper()}: {len(obj['data']['events'])} events, {len(obj['data']['venues'])} venues")

    # 合并 ALL.json（扁平结构，同样是最新格式）
    all_obj = {
        "version": _EXPORT_VERSION,
        "updatedAt": _now_ms(),
        "data": {
            "events": all_events,
            "venues": all_venues,
        },
    }
    all_path = os.path.join(OUT_DIR, "ALL.json")
    _write_json_uppercase(all_path, all_obj)
    print(f"  ALL: {len(all_events)} events, {len(all_venues)} venues")

    return {
        "success": True,
        "total": len(codes),
        "ok": len(per_city),
        "failed": len(codes) - len(per_city),
        "outputDir": OUT_DIR,
    }


def main():
    print("=" * 60)
    print("local-events-daily JSON 导出工具（最新格式 v%s）" % _EXPORT_VERSION)
    print(f"  数据目录: {BASE_DIR}")
    print(f"  输出目录: {OUT_DIR}")
    print("=" * 60)
    result = export_all()
    print("-" * 60)
    if result.get("success"):
        print(f"完成: {result['ok']}/{result['total']} 个城市已导出")
        print(f"目录: {result['outputDir']}")
    else:
        print("导出失败")
        sys.exit(1)


if __name__ == "__main__":
    main()
