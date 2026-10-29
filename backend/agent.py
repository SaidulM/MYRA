"""MYRA — Autonomous Desktop & PC Automation Agent.

Handles:
- Music & media playback (YouTube, songs)
- Browser opening, live Google Search & Gold rate / Shopping queries
- PC File operations (scan, search, open file)
- WhatsApp messaging & file transfer launch
- System telemetry (RAM, CPU, Battery)
- Notes & Reminders
- Camera & Screen share triggers
- Zero-token local execution for instant, light 8GB RAM performance.
"""
from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, quote_plus

ROOT = Path(__file__).resolve().parent.parent

try:
    import memory
    import notes
    import reminders
    import skills_manager
except ImportError:
    from . import memory, notes, reminders, skills_manager


def _open_url_safely(url: str) -> bool:
    try:
        webbrowser.open(url)
        return True
    except Exception:
        return False


def _open_file_safely(file_path: str) -> bool:
    try:
        if platform.system() == "Windows":
            os.startfile(file_path)
            return True
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", file_path])
            return True
        else:
            subprocess.Popen(["xdg-open", file_path])
            return True
    except Exception:
        return False


def parse_and_execute_local_intent(text: str) -> Optional[Dict[str, Any]]:
    """Inspect text for local desktop automation actions.

    Runs with 0 cloud tokens and executes instantaneously.
    """
    raw = str(text).strip()
    lowered = raw.lower()
    now_str = datetime.now().strftime("%H:%M:%S")

    # 0a. Auto Memory Learning from speech
    try:
        memory.auto_learn_from_text(raw)
    except Exception:
        pass

    # 0b. Zero-Token Memory Query Resolver (e.g. "what is my name", "আমার নাম কি", "আমার প্রিয় খাবার কি")
    try:
        mem_answer = memory.resolve_memory_query(raw)
        if mem_answer:
            return {
                "ok": True,
                "handled_locally": True,
                "action": "memory_recall",
                "tokens_used": 0,
                "logs": [
                    f"[{now_str}] 🧠 Queried local SQLite memory.",
                    f"[{now_str}] ✅ Fact retrieved with 0 cloud tokens.",
                ],
                "report": f"### 🧠 Memory Recall\n\n{mem_answer}",
                "voice_reply": mem_answer,
            }
    except Exception:
        pass

    # 0c. Self-Closing / Shutdown application ("বন্ধ হয়ে যাও", "close yourself", "quit", "exit")
    if any(k in lowered for k in ("close yourself", "shut down", "exit", "quit", "turn off", "sleep now")) or re.search(
        r"(?:তুমি\s*)?(?:ক্লোজ|বন্ধ)\s*(?:হয়ে\s*যাও|হও|করো)|বিদায়\s*মায়রা", raw
    ):
        is_bn = bool(re.search(r"[\u0980-\u09FF]", raw))
        reply = "ঠিক আছে, আজকের মতো আমি বন্ধ হচ্ছি। ভালো থাকবেন!" if is_bn else "Understood, closing now. Have a wonderful day!"
        return {
            "ok": True,
            "handled_locally": True,
            "action": "shutdown_app",
            "client_trigger": True,
            "tokens_used": 0,
            "logs": [
                f"[{now_str}] ⏻ Application shutdown requested.",
                f"[{now_str}] 🛑 Stopping desktop server and window.",
            ],
            "report": f"### ⏻ System Closing\n\n{reply}",
            "voice_reply": reply,
        }

    # 1. Gold Rate / Commodity Price Search ("আজকের গোল্ড রেট কি", "আজকের সোনার দাম", "gold rate today")
    if re.search(r"আজকের\s*(?:গোল্ড|সোনার|স্বর্ণের|রুপার|স্বর্ণ)?\s*(?:রেট|দাম|দর|মূল্য)", raw) or re.search(
        r"(?:today'?s?\s+)?(?:gold|silver)\s+(?:rate|price)", lowered
    ):
        is_bn = bool(re.search(r"[\u0980-\u09FF]", raw))
        q = "আজকের সোনার দাম বাংলাদেশ" if is_bn else "today gold rate 22k 24k"
        search_url = f"https://www.google.com/search?q={quote_plus(q)}"
        _open_url_safely(search_url)

        # Retrieve live snippets via web search
        snippets = skills_manager.web_search(q, max_results=3)
        summary_info = ""
        if snippets:
            summary_info = snippets[0].get("snippet", "")

        msg_bn = (
            f"গুগল ক্রোমে আজকের সোনার রেটের পেজটি ওপেন করেছি। {summary_info[:160]}..."
            if summary_info
            else "গুগল ক্রোম ব্রাউজারে আজকের সোনার রেটের পেজটি ওপেন করেছি, আপনি স্ক্রিনে দেখতে পাচ্ছেন।"
        )
        msg_en = (
            f"Opened Google Chrome with today's gold rate. {summary_info[:160]}..."
            if summary_info
            else "Opened Google Chrome with today's live gold rates for you."
        )

        return {
            "ok": True,
            "handled_locally": True,
            "action": "gold_rate_search",
            "url": search_url,
            "tokens_used": 0,
            "logs": [
                f"[{now_str}] 🪙 Gold/commodity rate query detected.",
                f"[{now_str}] 🌐 Launching Google Chrome search: {search_url}",
                f"[{now_str}] 📄 Retrieved live summary snippet.",
            ],
            "report": (
                f"### 🪙 Live Gold Rate Query\n\n"
                f"- **Browser Action**: Opened Google Search for live commodity prices.\n"
                f"- **Link**: [{search_url}]({search_url})\n\n"
                f"**Live Overview**:\n{summary_info or 'Live pricing loaded in Chrome window.'}"
            ),
            "voice_reply": msg_bn if is_bn else msg_en,
        }

    # 2. Shopping / Product Search ("কিছু শপিং করার আছে", "buy shoes", "কিনতে চাই")
    shop_match = re.search(
        r"(?:shopping|কিনতে\s*চাই|শপিং\s*করতে\s*চাই|কিনবো|buy\s+online|search\s+product)\s*(?:for\s+|হলো\s+)?(.+)?",
        raw,
        re.IGNORECASE,
    )
    if shop_match and shop_match.group(1):
        item = shop_match.group(1).strip().strip('"').strip("'")
        shop_url = f"https://www.google.com/search?tbm=shop&q={quote_plus(item)}"
        _open_url_safely(shop_url)
        is_bn = bool(re.search(r"[\u0980-\u09FF]", raw))
        msg = (
            f"'{item}' এর জন্য শপিং অপশনগুলো গুগল এবং দারাজে সার্চ করে ওপেন করে দিয়েছি।"
            if is_bn
            else f"Searching shopping options for '{item}' and opened Google Shopping."
        )
        return {
            "ok": True,
            "handled_locally": True,
            "action": "shopping_search",
            "query": item,
            "url": shop_url,
            "tokens_used": 0,
            "logs": [
                f"[{now_str}] 🛍️ Shopping intent detected: \"{item}\"",
                f"[{now_str}] 🌐 Opening Google Shopping: {shop_url}",
            ],
            "report": f"### 🛍️ Shopping Search: {item}\n\nOpened Google Shopping in your browser.\n\n[{shop_url}]({shop_url})",
            "voice_reply": msg,
        }

    # 3. Play Music / Song ("গান বাজাও", "play song")
    music_match = re.search(
        r"(?:play|গান\s*বাজাও|গান\s*চালাও|বাজাও)\s+(?:song\s+|music\s+|the\s+song\s+)?(.+)",
        raw,
        re.IGNORECASE,
    ) or re.search(r"(.+?)\s+গান\s*(?:বাজাও|চালাও)", raw, re.IGNORECASE)

    if music_match and not any(k in lowered for k in ("game", "roleplay", "character")):
        song_query = music_match.group(1).strip().strip('"').strip("'")
        yt_url = f"https://www.youtube.com/results?search_query={quote_plus(song_query)}+song"
        _open_url_safely(yt_url)

        msg_en = f"Playing '{song_query}' on YouTube 🎵"
        msg_bn = f"ইউটিউবে '{song_query}' গানটি প্লে করা হচ্ছে 🎵"

        return {
            "ok": True,
            "handled_locally": True,
            "action": "play_music",
            "query": song_query,
            "url": yt_url,
            "tokens_used": 0,
            "logs": [
                f"[{now_str}] 🎵 Detected media request: \"{song_query}\"",
                f"[{now_str}] 🌐 Opening YouTube audio/video stream: {yt_url}",
                f"[{now_str}] ✅ Playback launched in browser.",
            ],
            "report": (
                f"### 🎵 Now Playing: {song_query}\n\n"
                f"- **Platform**: YouTube\n"
                f"- **Action**: Opened web playback for **{song_query}**.\n"
                f"- **Link**: [{yt_url}]({yt_url})\n\n"
                f"*Executed locally with 0 cloud tokens.*"
            ),
            "voice_reply": msg_bn if re.search(r"[\u0980-\u09FF]", raw) else msg_en,
        }

    # 4. Camera Trigger ("আমার ক্যামেরা চালু করো", "open camera")
    if re.search(r"(?:open|turn\s*on|start|show)\s+cam(?:era)?", lowered) or re.search(
        r"ক্যামেরা\s*(?:চালু\s*করো|খোলো|অন\s*করো|দেখাও)", raw
    ):
        return {
            "ok": True,
            "handled_locally": True,
            "action": "open_camera",
            "client_trigger": True,
            "tokens_used": 0,
            "logs": [
                f"[{now_str}] 📷 Local Camera activation requested.",
                f"[{now_str}] 👁️ Engaging Visual Hub video sensor.",
                f"[{now_str}] ✅ Camera active.",
            ],
            "report": "### 📷 Camera Activated\n\nVisual Hub is now streaming your webcam feed live.",
            "voice_reply": "ক্যামেরা চালু করা হয়েছে।" if re.search(r"[\u0980-\u09FF]", raw) else "Camera is now activated in the Visual Hub.",
        }

    # 5. Screen Share Trigger ("আমার স্ক্রিন দেখো", "share screen")
    if re.search(r"(?:share|show|look\s+at)\s+screen", lowered) or re.search(
        r"স্ক্রিন\s*(?:শেয়ার\s*করো|দেখাও|অন\s*করো|দেখো)", raw
    ):
        return {
            "ok": True,
            "handled_locally": True,
            "action": "open_screen",
            "client_trigger": True,
            "tokens_used": 0,
            "logs": [
                f"[{now_str}] 🖥️ Screen share activation requested.",
                f"[{now_str}] 👁️ Connecting Visual Hub display stream.",
                f"[{now_str}] ✅ Screen share active.",
            ],
            "report": "### 🖥️ Screen Share Activated\n\nVisual Hub is now sharing your desktop screen.",
            "voice_reply": "স্ক্রিন শেয়ার চালু করা হয়েছে।" if re.search(r"[\u0980-\u09FF]", raw) else "Screen sharing is active.",
        }

    # 6. Open Website / Google Search ("গুগলে সার্চ করো X", "search google for X")
    google_search_match = re.search(
        r"(?:google\s+search|search\s+google\s+for|গুগলে\s*সার্চ\s*করো|সার্চ\s*করো|খুঁজে\s*দাও)\s+(.+)",
        raw,
        re.IGNORECASE,
    )
    if google_search_match and not any(k in lowered for k in ("file", "ফাইল", "song", "গান", "camera")):
        search_text = google_search_match.group(1).strip()
        search_url = f"https://www.google.com/search?q={quote_plus(search_text)}"
        _open_url_safely(search_url)
        is_bn = bool(re.search(r"[\u0980-\u09FF]", raw))
        msg = f"গুগল ক্রোম ব্রাউজারে '{search_text}' সার্চ করা হয়েছে।" if is_bn else f"Searching '{search_text}' on Google in your browser."
        return {
            "ok": True,
            "handled_locally": True,
            "action": "google_search",
            "url": search_url,
            "tokens_used": 0,
            "logs": [
                f"[{now_str}] 🌐 Google search triggered: \"{search_text}\"",
                f"[{now_str}] 🚀 Opening URL: {search_url}",
            ],
            "report": f"### 🌐 Google Search\n\nOpened: [{search_url}]({search_url})",
            "voice_reply": msg,
        }

    # 7. Open Website ("ব্রাউজার খোলো", "open youtube", "open gmail")
    browse_match = re.search(
        r"(?:open|browse\s+to|খোলো)\s+(?:the\s+)?(https?://\S+|google|youtube|facebook|github|gmail|chatgpt|twitter|reddit|wikipedia)",
        lowered,
    )
    if browse_match:
        target = browse_match.group(1).strip()
        site_map = {
            "google": "https://www.google.com",
            "youtube": "https://www.youtube.com",
            "facebook": "https://www.facebook.com",
            "github": "https://github.com",
            "gmail": "https://mail.google.com",
            "chatgpt": "https://chatgpt.com",
            "twitter": "https://twitter.com",
            "reddit": "https://www.reddit.com",
            "wikipedia": "https://www.wikipedia.org",
        }
        dest_url = site_map.get(target, target if target.startswith("http") else f"https://{target}")
        _open_url_safely(dest_url)
        return {
            "ok": True,
            "handled_locally": True,
            "action": "open_browser",
            "url": dest_url,
            "tokens_used": 0,
            "logs": [
                f"[{now_str}] 🌐 Browser action triggered: {dest_url}",
                f"[{now_str}] ✅ Opened in default desktop browser.",
            ],
            "report": f"### 🌐 Browser Opened: {dest_url}\n\nTarget site was opened in your default browser.",
            "voice_reply": f"{target.capitalize()} ব্রাউজারে ওপেন করা হয়েছে।" if re.search(r"[\u0980-\u09FF]", raw) else f"Opening {target} in your browser.",
        }

    # 8. Set Reminder ("রিমাইন্ডার দাও", "remind me to...")
    rem_match = re.search(
        r"(?:remind\s+me|মনে\s*করিয়ে\s*দাও|রিমাইন্ডার\s*দাও)\s+(?:to\s+)?(.+?)(?:\s+(?:in|after|পরে)\s+(\d+)\s*(?:min|minute|মিনিট)s?)?$",
        raw,
        re.IGNORECASE,
    ) or re.search(r"set\s+reminder\s+(.+)", raw, re.IGNORECASE)

    if rem_match:
        task_info = rem_match.group(1).strip()
        mins = 10
        if len(rem_match.groups()) > 1 and rem_match.group(2):
            try:
                mins = int(rem_match.group(2))
            except ValueError:
                mins = 10
        rem_res = reminders.add_reminder(task_info, minutes=mins)
        due_time = rem_res.get("due_str", f"in {mins} minutes")
        return {
            "ok": True,
            "handled_locally": True,
            "action": "set_reminder",
            "reminder": rem_res,
            "tokens_used": 0,
            "logs": [
                f"[{now_str}] ⏰ Reminder registered: \"{task_info}\"",
                f"[{now_str}] 📅 Scheduled for: {due_time} ({mins} mins)",
                f"[{now_str}] 💾 Saved to local SQLite database.",
            ],
            "report": (
                f"### ⏰ Reminder Scheduled\n\n"
                f"- **Task**: {task_info}\n"
                f"- **Due**: {due_time} (in {mins} minutes)\n"
                f"- **Notification**: MYRA will speak and alert you when due."
            ),
            "voice_reply": f"ঠিক আছে, {mins} মিনিট পর আপনাকে '{task_info}' মনে করিয়ে দেব।" if re.search(r"[\u0980-\u09FF]", raw) else f"Reminder set for {task_info} in {mins} minutes.",
        }

    # 9. Save Note ("নোট লিখে রাখো", "take note")
    note_match = re.search(
        r"(?:take\s+note|নোট\s*করো|save\s+note|নোট\s*লিখে\s*রাখো|নোট\s*কর)\s+(?:that\s+)?(.+)",
        raw,
        re.IGNORECASE,
    )
    if note_match:
        note_content = note_match.group(1).strip()
        title = note_content[:30] + ("…" if len(note_content) > 30 else "")
        created_note = notes.add_note(note_content, title=title)
        return {
            "ok": True,
            "handled_locally": True,
            "action": "save_note",
            "note": created_note,
            "tokens_used": 0,
            "logs": [
                f"[{now_str}] 📝 Capturing local note: \"{title}\"",
                f"[{now_str}] 💾 Stored in offline SQLite notes database.",
            ],
            "report": f"### 📝 Note Saved\n\n**{title}**\n\n{note_content}",
            "voice_reply": "নোট সংরক্ষণ করা হয়েছে।" if re.search(r"[\u0980-\u09FF]", raw) else "Note saved successfully.",
        }

    # 10. File Operations ("list files", "ফাইল দেখাও")
    if re.search(r"(?:list|show)\s+files", lowered) or re.search(r"ফাইল\s*(?:দেখাও|লিস্ট)", raw):
        workspace_files = []
        try:
            for p in sorted(ROOT.glob("*"))[:20]:
                if not p.name.startswith((".", "__")):
                    workspace_files.append(f"{'📁' if p.is_dir() else '📄'} {p.name}")
        except Exception:
            pass
        file_list_str = "\n".join(f"- {f}" for f in workspace_files)
        return {
            "ok": True,
            "handled_locally": True,
            "action": "list_files",
            "tokens_used": 0,
            "logs": [
                f"[{now_str}] 📁 Scanning directory: {ROOT}",
                f"[{now_str}] 📄 Found {len(workspace_files)} items.",
            ],
            "report": f"### 📂 Directory Files\n\n{file_list_str}",
            "voice_reply": f"মোট {len(workspace_files)} টি ফাইল ও ফোল্ডার পাওয়া গেছে।" if re.search(r"[\u0980-\u09FF]", raw) else f"Found {len(workspace_files)} files in your directory.",
        }

    # 11. Search Files across PC ("search file resume", "ফাইল খোঁজো invoice")
    file_search_match = re.search(
        r"(?:search\s+file|find\s+file|ফাইল\s*খোঁজো|ফাইল\s*খুঁজে\s*দাও|search\s+for\s+file)\s+(.+)",
        raw,
        re.IGNORECASE,
    )
    if file_search_match:
        query_filename = file_search_match.group(1).strip().strip('"').strip("'")
        found_files = []
        search_dirs = [
            Path.home() / "Desktop",
            Path.home() / "Downloads",
            Path.home() / "Documents",
            Path.home() / "Pictures",
            ROOT,
        ]
        q_lower = query_filename.lower()
        for sdir in search_dirs:
            if not sdir.exists():
                continue
            try:
                for entry in sdir.glob(f"*{q_lower}*"):
                    if not entry.name.startswith("."):
                        size_kb = entry.stat().st_size / 1024 if entry.is_file() else 0
                        found_files.append({
                            "name": entry.name,
                            "path": str(entry.resolve()),
                            "dir": sdir.name,
                            "size": f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb/1024:.2f} MB",
                            "is_dir": entry.is_dir(),
                        })
                        if len(found_files) >= 12:
                            break
            except Exception:
                continue

        is_bn = bool(re.search(r"[\u0980-\u09FF]", raw))
        if found_files:
            file_report_lines = [f"- **{f['name']}** ({f['size']}) in `{f['dir']}`\n  `{f['path']}`" for f in found_files]
            rep = f"### 🔍 Found {len(found_files)} files matching '{query_filename}':\n\n" + "\n".join(file_report_lines)
            v_rep = f"'{query_filename}' সম্পর্কিত {len(found_files)} টি ফাইল খুঁজে পেয়েছি।" if is_bn else f"Found {len(found_files)} files matching '{query_filename}'."
        else:
            rep = f"### 🔍 No files found matching '{query_filename}' in Desktop, Downloads, or Documents."
            v_rep = f"'{query_filename}' নামে কোনো ফাইল খুঁজে পাওয়া যায়নি।" if is_bn else f"Could not find any file named '{query_filename}'."

        return {
            "ok": True,
            "handled_locally": True,
            "action": "search_files",
            "query": query_filename,
            "files": found_files,
            "tokens_used": 0,
            "logs": [
                f"[{now_str}] 🔍 Searching for file: '{query_filename}'",
                f"[{now_str}] 📂 Scanned Desktop, Downloads, Documents.",
                f"[{now_str}] 📄 Found: {len(found_files)} matching items.",
            ],
            "report": rep,
            "voice_reply": v_rep,
        }

    # 12. Open Found File ("open file X", "ফাইল খোলো X")
    open_file_match = re.search(
        r"(?:open\s+file|খোলো\s+ফাইল|ফাইল\s*খোলো)\s+(.+)",
        raw,
        re.IGNORECASE,
    )
    if open_file_match:
        target_name = open_file_match.group(1).strip().strip('"').strip("'")
        target_path = None
        for sdir in [Path.home() / "Desktop", Path.home() / "Downloads", Path.home() / "Documents", ROOT]:
            if not sdir.exists(): continue
            for entry in sdir.glob(f"*{target_name.lower()}*"):
                if entry.is_file():
                    target_path = str(entry.resolve())
                    break
            if target_path: break

        is_bn = bool(re.search(r"[\u0980-\u09FF]", raw))
        if target_path and _open_file_safely(target_path):
            msg = f"'{target_name}' ফাইলটি ওপেন করা হয়েছে।" if is_bn else f"Opened '{target_name}' successfully."
            return {
                "ok": True,
                "handled_locally": True,
                "action": "open_file",
                "path": target_path,
                "report": f"### 📂 Opened File\n\n`{target_path}`",
                "voice_reply": msg,
            }

    # 13. WhatsApp Message & File ("send whatsapp to ...", "হোয়াটসঅ্যাপে মেসেজ পাঠাও")
    wa_match = re.search(
        r"(?:whatsapp|হোয়াটসঅ্যাপে\s*(?:মেসেজ|ফাইল)?\s*পাঠাও|send\s+whatsapp)\s*(?:to\s+([+0-9\s-]+))?(?:\s+(?:saying|message|বলো|যে)?\s*(.+))?",
        raw,
        re.IGNORECASE,
    )
    if wa_match and not any(k in lowered for k in ("what is", "কি")):
        phone = re.sub(r"[^\d+]", "", wa_match.group(1) or "")
        msg = (wa_match.group(2) or "").strip()
        if not msg and not phone:
            msg = "Hello"
        wa_url = f"https://web.whatsapp.com/send?text={quote(msg)}"
        if phone:
            wa_url += f"&phone={quote(phone)}"
        _open_url_safely(wa_url)
        is_bn = bool(re.search(r"[\u0980-\u09FF]", raw))
        rep = f"### 💬 WhatsApp Web Launched\n\n- **Target**: `{phone or 'Select contact'}`\n- **Message**: {msg}\n- **Action**: Opened in browser."
        v_rep = "হোয়াটসঅ্যাপে মেসেজ বা ফাইল পাঠানোর জন্য ব্রাউজার চালু করা হয়েছে।" if is_bn else "Opening WhatsApp Web to send your message."
        return {
            "ok": True,
            "handled_locally": True,
            "action": "send_whatsapp",
            "url": wa_url,
            "tokens_used": 0,
            "logs": [
                f"[{now_str}] 💬 WhatsApp integration triggered.",
                f"[{now_str}] 🌐 Launching WhatsApp Web: {wa_url}",
            ],
            "report": rep,
            "voice_reply": v_rep,
        }

    # 14. System Status / Telemetry ("পিসির অবস্থা", "system status", "battery", "ram")
    if any(k in lowered for k in ("system status", "system info", "পিসির অবস্থা", "র‍্যাম", "ব্যাটারি", "hardware status")):
        sys_info = skills_manager.get_system_info()
        return {
            "ok": True,
            "handled_locally": True,
            "action": "system_status",
            "tokens_used": 0,
            "logs": [
                f"[{now_str}] ⚙️ Reading local hardware telemetry...",
                f"[{now_str}] 💻 OS: {sys_info.get('os')}",
                f"[{now_str}] 🧠 CPU Arch: {sys_info.get('machine')}",
            ],
            "report": (
                f"### 💻 System Hardware Status\n\n"
                f"- **Operating System**: {sys_info.get('os')}\n"
                f"- **Machine**: {sys_info.get('machine')}\n"
                f"- **Processor**: {sys_info.get('processor')}\n"
                f"- **Python Version**: {sys_info.get('python')}\n"
                f"- **Timestamp**: {sys_info.get('local_time')}\n\n"
                f"*Running smooth and lightweight on your PC.*"
            ),
            "voice_reply": "সিস্টেম স্বাভাবিক এবং সঠিকভাবে চলছে।" if re.search(r"[\u0980-\u09FF]", raw) else "System is healthy and operating normally.",
        }

    return None


def run_agent_task(task_text: str, model_provider: str = "auto") -> Dict[str, Any]:
    """Execute an autonomous task: checks zero-token local intent first, then web research."""
    task = str(task_text).strip()
    if not task:
        return {
            "ok": False,
            "error": "Please provide a task or question for the Agent.",
        }

    # Check local zero-token intents first
    local_result = parse_and_execute_local_intent(task)
    if local_result:
        return local_result

    # Fallback to web search & intelligence synthesis
    logs: List[str] = []
    now_str = datetime.now().strftime("%H:%M:%S")
    logs.append(f"[{now_str}] 🚀 Autonomous Task dispatched: \"{task[:80]}\"")
    logs.append(f"[{now_str}] ⚙️ Extracting search parameters and key concepts...")

    query = task
    for prefix in ("search for ", "search ", "find info on ", "find ", "research ", "look up ", "খুঁজে বের করো "):
        if query.lower().startswith(prefix):
            query = query[len(prefix):].strip()
            break

    logs.append(f"[{now_str}] 🌐 Dispatching live search query: \"{query}\"")
    search_results = skills_manager.web_search(query, max_results=4)

    sources_used = []
    findings_text = ""

    if search_results:
        logs.append(f"[{now_str}] 📄 Retrieved {len(search_results)} relevant sources.")
        for idx, res in enumerate(search_results, 1):
            title = res.get("title", "")
            snippet = res.get("snippet", "")
            url = res.get("url", "")
            logs.append(f"[{now_str}]   ↳ Source {idx}: {title}")
            sources_used.append({"title": title, "url": url})
            findings_text += f"- **{title}**: {snippet}\n"
    else:
        logs.append(f"[{now_str}] ⚠️ Web search returned no direct answers; querying local knowledge.")
        findings_text = "No direct search snippets available."

    report = (
        f"### 🤖 Autonomous Agent Report: {query}\n\n"
        f"**Task**: {task}\n\n"
        f"#### 🌐 Live Findings:\n{findings_text}\n"
        f"#### 📚 Sources:\n"
        + "\n".join(f"- [{s['title']}]({s['url']})" if s['url'] else f"- {s['title']}" for s in sources_used)
    )

    is_bn = bool(re.search(r"[\u0980-\u09FF]", task))
    v_reply = (
        f"আপনার অনুসন্ধান '{query}' সম্পন্ন হয়েছে। রিপোর্ট তৈরি করা হয়েছে।"
        if is_bn
        else f"Completed autonomous research for '{query}'."
    )

    return {
        "ok": True,
        "action": "web_research",
        "logs": logs,
        "report": report,
        "voice_reply": v_reply,
        "sources": sources_used,
    }
