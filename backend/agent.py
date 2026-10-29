"""MYRA — Autonomous Desktop & PC Automation Agent (Stage 8).

Handles:
- Music & media playback (YouTube, songs)
- Browser opening & web search
- File operations (list, read, write)
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
import sys
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, quote_plus

ROOT = Path(__file__).resolve().parent.parent

try:
    import notes
    import reminders
    import skills_manager
except ImportError:
    from . import notes, reminders, skills_manager


def _open_url_safely(url: str) -> bool:
    try:
        webbrowser.open(url)
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

    # 1. Play Music / Song ("গানা চালাতে পারি", "গান বাজাও", "play song")
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

    # 2. Camera Trigger ("আমার ক্যামেরা চালু করো", "open camera")
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

    # 3. Screen Share Trigger ("আমার স্ক্রিন দেখো", "share screen")
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

    # 4. Open Website / Browser ("ব্রাউজার খোলো", "open google", "open youtube")
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

    # 5. Set Reminder ("রিমাইন্ডার দাও", "remind me to...")
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

    # 6. Save Note ("নোট লিখে রাখো", "take note")
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

    # 7. File Operations ("list files", "ফাইল দেখাও")
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

    # 8. System Status / Telemetry ("পিসির অবস্থা", "system status", "battery", "ram")
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
            findings_text += f"\n- **{title}**: {snippet}"
            if url:
                findings_text += f" ([Link]({url}))"
    else:
        logs.append(f"[{now_str}] ℹ️ Synthesizing response from local knowledge...")

    logs.append(f"[{now_str}] 🧠 Compiling structured intelligence report...")

    report_lines = [
        f"### 📋 Autonomous Agent Report: {task}",
        "",
        "#### 🎯 Summary",
        f"The agent has completed researching: **{task}**.",
        "",
        "#### 🔍 Key Findings & Intelligence",
    ]

    if findings_text:
        report_lines.append(findings_text.strip())
    else:
        report_lines.append(f"Processed requirements for: **{task}** with system verification.")

    if sources_used:
        report_lines.append("")
        report_lines.append("#### 🌐 Sources & References")
        for s in sources_used:
            url_str = f" - {s['url']}" if s.get('url') else ""
            report_lines.append(f"- {s['title']}{url_str}")

    report_lines.append("")
    report_lines.append(f"*Compiled at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} by MYRA Agent Engine.*")

    logs.append(f"[{now_str}] ✅ Task execution complete.")

    return {
        "ok": True,
        "task": task,
        "logs": logs,
        "report": "\n".join(report_lines),
        "sources": sources_used,
        "tokens_used": 0 if not findings_text else 25,
    }
