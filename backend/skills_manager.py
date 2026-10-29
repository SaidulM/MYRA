"""MYRA — Skills Manager & Registry (Stage 7).

Manages extensible skills that MYRA can use to assist the user.
Built using standard library and free lightweight endpoints.
"""
from __future__ import annotations

import ast
import json
import math
import operator
import os
import platform
import ssl
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

def _safe_urlopen(req, timeout=8):
    try:
        return urlopen(req, timeout=timeout)
    except (ssl.SSLError, URLError):
        ctx = ssl._create_unverified_context()
        return urlopen(req, timeout=timeout, context=ctx)

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"


# ---------- Safe Math Evaluator for Calculator Skill ----------
_MATH_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_math_node(node: Any) -> float:
    if isinstance(node, ast.Num):  # Python < 3.8
        return node.n
    if isinstance(node, ast.Constant):  # Python 3.8+
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("Non-numeric constant")
    if isinstance(node, ast.BinOp):
        op = type(node.op)
        if op in _MATH_OPERATORS:
            left = _eval_math_node(node.left)
            right = _eval_math_node(node.right)
            return _MATH_OPERATORS[op](left, right)
        raise ValueError(f"Unsupported operator: {op}")
    if isinstance(node, ast.UnaryOp):
        op = type(node.op)
        if op in _MATH_OPERATORS:
            return _MATH_OPERATORS[op](_eval_math_node(node.operand))
        raise ValueError(f"Unsupported unary operator: {op}")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        fn = node.func.id.lower()
        args = [_eval_math_node(a) for a in node.args]
        math_fns = {
            "sqrt": math.sqrt,
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "log": math.log,
            "abs": abs,
            "round": round,
        }
        if fn in math_fns:
            return math_fns[fn](*args)
        raise ValueError(f"Unsupported math function: {fn}")
    raise ValueError(f"Unsupported expression element: {type(node)}")


def safe_calculate(expression: str) -> str:
    """Safely calculate a mathematical expression."""
    expr = expression.strip()
    if not expr:
        return "Please provide a valid math expression."
    try:
        parsed = ast.parse(expr, mode="eval")
        res = _eval_math_node(parsed.body)
        if isinstance(res, float) and res.is_integer():
            res = int(res)
        return str(res)
    except Exception as exc:
        return f"Calculation error: {exc}"


# ---------- Web Search Skill (DuckDuckGo / Wikipedia free) ----------
def web_search(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """Free web search using DuckDuckGo Instant Answer API / HTML."""
    q = query.strip()
    if not q:
        return []
    url = f"https://api.duckduckgo.com/?q={quote_plus(q)}&format=json&no_html=1&skip_disambig=1"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MYRA/1.0"}
    results: List[Dict[str, str]] = []

    try:
        req = Request(url, headers=headers)
        with _safe_urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))

        if data.get("AbstractText"):
            results.append({
                "title": data.get("Heading") or q,
                "snippet": data["AbstractText"],
                "url": data.get("AbstractURL") or "",
            })

        for item in data.get("RelatedTopics", []):
            if "Text" in item and "FirstURL" in item:
                results.append({
                    "title": item["Text"].split(" - ")[0] if " - " in item["Text"] else item["Text"][:60],
                    "snippet": item["Text"],
                    "url": item["FirstURL"],
                })
            elif "Topics" in item:
                for sub in item["Topics"]:
                    if "Text" in sub:
                        results.append({
                            "title": sub["Text"][:60],
                            "snippet": sub["Text"],
                            "url": sub.get("FirstURL", ""),
                        })
            if len(results) >= max_results:
                break
    except Exception:
        pass

    # If instant answer returned nothing, fallback to Wikipedia summary
    if not results:
        try:
            wiki_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote_plus(q)}"
            req = Request(wiki_url, headers=headers)
            with _safe_urlopen(req, timeout=8) as resp:
                wiki_data = json.loads(resp.read().decode("utf-8", errors="ignore"))
                if wiki_data.get("extract"):
                    results.append({
                        "title": wiki_data.get("title", q),
                        "snippet": wiki_data.get("extract", ""),
                        "url": wiki_data.get("content_urls", {}).get("desktop", {}).get("page", ""),
                    })
        except Exception:
            pass

    return results[:max_results]


# ---------- Weather Skill (wttr.in free JSON) ----------
def get_weather(location: str = "") -> str:
    loc = location.strip() or ""
    url = f"https://wttr.in/{quote_plus(loc)}?format=j1" if loc else "https://wttr.in/?format=j1"
    headers = {"User-Agent": "MYRA-Assistant/1.0"}
    try:
        req = Request(url, headers=headers)
        with _safe_urlopen(req, timeout=7) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="ignore"))
            current = data.get("current_condition", [{}])[0]
            temp_c = current.get("temp_C", "?")
            desc = current.get("weatherDesc", [{}])[0].get("value", "Clear")
            humidity = current.get("humidity", "?")
            wind_kph = current.get("windspeedKmph", "?")
            area = ""
            try:
                area = data.get("nearest_area", [{}])[0].get("areaName", [{}])[0].get("value", "")
            except Exception:
                pass
            loc_label = f"in {area or loc}" if (area or loc) else "currently"
            return f"Weather {loc_label}: {desc}, {temp_c}°C, Humidity: {humidity}%, Wind: {wind_kph} km/h."
    except Exception as exc:
        return f"Could not retrieve weather: {exc}"


# ---------- System Info Skill ----------
def get_system_info() -> Dict[str, str]:
    return {
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "machine": platform.machine(),
        "processor": platform.processor() or "Unknown CPU",
        "python": sys.version.split()[0],
        "node": platform.node(),
        "local_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# ---------- Skills Registry ----------
SKILLS = {
    "browser_agent": {
        "id": "browser_agent",
        "name": "Browser Agent",
        "description": "Performs web searches, research, and reports for you.",
        "icon": "🌐",
        "default": True,
    },
    "news_reader": {
        "id": "news_reader",
        "name": "News Reader",
        "description": "Reads today's headlines aloud on request from live RSS.",
        "icon": "📰",
        "default": True,
    },
    "note_helper": {
        "id": "note_helper",
        "name": "Note Helper",
        "description": "Takes, finds, and organizes your personal notes locally.",
        "icon": "📝",
        "default": True,
    },
    "calculator": {
        "id": "calculator",
        "name": "Smart Calculator",
        "description": "Solves math equations and expressions accurately.",
        "icon": "🔢",
        "default": True,
    },
    "camera_vision": {
        "id": "camera_vision",
        "name": "Camera Vision",
        "description": "Understands what the camera shows (only with permission).",
        "icon": "📷",
        "default": False,
    },
    "system_info": {
        "id": "system_info",
        "name": "System Diagnostics",
        "description": "Checks system performance, specs, and status.",
        "icon": "⚙️",
        "default": True,
    },
    "weather": {
        "id": "weather",
        "name": "Weather Reporter",
        "description": "Live weather reports for any city worldwide.",
        "icon": "🌤️",
        "default": True,
    },
}


def list_skills() -> List[Dict[str, Any]]:
    return list(SKILLS.values())
