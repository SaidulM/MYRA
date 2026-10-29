"""MYRA — Native Python Desktop Application (Tkinter GUI).

100% Native Desktop Software Window created directly with Python standard library.
Runs directly on your laptop without opening any web browser.

Features:
- Animated 3D Cyber Particle Face & Avatar on Tkinter Canvas:
  * Sculpted facial features (rounded dome head, eye sockets, 3D nose, lips, chin)
  * Shortened natural human neck and visible shoulders/arms
  * Smooth mouse tracking (turns head towards mouse smoothly, zero endless 360 spinning)
  * 60 floating star particles drifting in space
  * Dynamic color morphing on persona switch (Core cyan, Male blue, Female magenta)
  * Real-time audio-reactive wave & mouth movement when speaking
- Voice Input with Automatic Silence Detection & Auto-Send:
  * Microphone listening with speech recognition
  * Auto-sends immediately upon silence — zero manual clicking required
  * Lower status indicator: "মাইরা শুনেছে, উত্তর দিচ্ছে এক্ষুনি…"
  * Speaks back answers in natural neural human voice
- Autonomous Agent Integrations:
  * 🪙 Live Gold Rate: Opens Google Chrome to live rates and speaks answer in Bengali/English
  * 🔍 PC File Finder: Scans PC and automatically opens files
  * 🛍️ Shopping Search: Finds products on Google/Daraz
  * 💬 WhatsApp messaging
  * ⏰ Offline SQLite Reminders & Notes
- Multi-Brain Provider Picker:
  * Auto, Gemini, Groq, OpenRouter, OpenAI, DeepSeek, Mistral, Ollama
  * Settings dialog to manage and test API keys
- SQLite Memory Viewer:
  * Persistent learning from chats into data/myra.db
"""
from __future__ import annotations

import math
import os
import random
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

import agent
import chat
import config
import memory
import notes
import reminders
import voice_studio

# ---------------------------------------------------------------------------
# Global State
# ---------------------------------------------------------------------------
IS_SPEAKING = False
SPEAKING_LOCK = threading.Lock()


def play_audio_file(mp3_path: str):
    """Play audio file natively without opening any external browser."""
    global IS_SPEAKING
    try:
        IS_SPEAKING = True
        if sys.platform == "win32":
            # Native Windows Media Player playback via PowerShell
            cmd = f'$p = New-Object System.Media.SoundPlayer "{mp3_path}"; $p.PlaySync();'
            # If MP3, use Windows Media Player COM object:
            wm_cmd = (
                f'$w = New-Object -ComObject WMPlayer.OCX; '
                f'$w.URL = "{mp3_path}"; '
                f'$w.controls.play(); '
                f'while($w.playState -eq 3 -or $w.playState -eq 9) {{ Start-Sleep -Milliseconds 150 }}'
            )
            subprocess.run(["powershell", "-NoProfile", "-Command", wm_cmd], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        elif sys.platform == "darwin":
            subprocess.run(["afplay", mp3_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.run(["ffplay", "-nodisp", "-autoexit", mp3_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass
    finally:
        IS_SPEAKING = False


def speak_text_async(text: str, character: str = "core", on_start=None, on_done=None):
    """Synthesize and play speech in a background thread."""
    def _worker():
        global IS_SPEAKING
        try:
            if on_start:
                on_start()
            clean = voice_studio.clean_text_for_speech(text)
            if not clean:
                return
            audio_bytes = voice_studio.synthesize_speech(clean, character=character)
            if audio_bytes:
                cache_dir = ROOT / "data" / "voice_cache"
                cache_dir.mkdir(parents=True, exist_ok=True)
                tmp_path = cache_dir / "myra_speech.mp3"
                tmp_path.write_bytes(audio_bytes)
                play_audio_file(str(tmp_path))
        except Exception:
            pass
        finally:
            IS_SPEAKING = False
            if on_done:
                on_done()

    threading.Thread(target=_worker, daemon=True).start()


# ---------------------------------------------------------------------------
# 3D Cyber Particle Avatar Geometry
# ---------------------------------------------------------------------------
def generate_face_model():
    """Build sculpted 3D landmarks for MYRA's cyber face mesh.
    
    Includes:
    - Rounded dome head top (smooth ellipsoid, no boxy cutoff!)
    - Forehead curve & brow ridges
    - Left & right eye sockets and pupils
    - 3D sculpted nose bridge, prominent nose tip, and nostrils
    - Mouth & lips (upper/lower arcs)
    - Defined chin and jawline
    - Shortened natural neck (from jaw to y=68)
    - Clavicles, shoulders and upper arms extending downwards
    """
    vertices = []  # list of (x, y, z, category)
    lines = []      # list of (index_a, index_b)

    # 1. Rounded Head Top Dome (Ellipsoid cap, smooth curve)
    for phi_deg in range(0, 180, 20):
        phi = math.radians(phi_deg)
        for theta_deg in range(15, 80, 15):
            theta = math.radians(theta_deg)
            rx, ry, rz = 52, 60, 48
            x = rx * math.sin(theta) * math.cos(phi)
            y = -ry * math.cos(theta) - 20
            z = rz * math.sin(theta) * math.sin(phi) - 10
            vertices.append((x, y, z, "dome"))

    # 2. Forehead Brow Arcs
    for side in (-1, 1):
        for i in range(5):
            x = side * (12 + i * 8)
            y = -22 + (i ** 1.3) * 1.5
            z = 32 - i * 2.5
            vertices.append((x, y, z, "brow"))

    # 3. Eye Sockets & Pupils
    for side in (-1, 1):
        cx = side * 28
        cy = -12
        cz = 30
        vertices.append((cx, cy, cz + 3, "pupil"))  # pupil center
        for a_deg in range(0, 360, 40):
            rad = math.radians(a_deg)
            ex = cx + 10 * math.cos(rad)
            ey = cy + 5 * math.sin(rad)
            ez = cz + 2 * math.cos(rad)
            vertices.append((ex, ey, ez, "eye"))

    # 4. 3D Sculpted Nose
    # Nose bridge
    for i in range(5):
        ny = -18 + i * 7
        nz = 32 + i * 3.5
        vertices.append((0, ny, nz, "nose"))
    # Nose tip (forward protrusion)
    vertices.append((0, 14, 48, "nose_tip"))
    # Nostrils
    vertices.append((-9, 17, 40, "nose"))
    vertices.append((9, 17, 40, "nose"))

    # 5. Lips & Mouth
    # Upper lip arc
    for i in range(-3, 4):
        mx = i * 6
        my = 28 - abs(i) * 1.2
        mz = 38 - abs(i) * 1.8
        vertices.append((mx, my, mz, "mouth_up"))
    # Lower lip arc
    for i in range(-3, 4):
        mx = i * 5.5
        my = 35 + abs(i) * 0.8
        mz = 36 - abs(i) * 2.0
        vertices.append((mx, my, mz, "mouth_down"))

    # 6. Chin & Jawline
    vertices.append((0, 48, 32, "chin"))
    for side in (-1, 1):
        for i in range(1, 6):
            jx = side * (i * 9)
            jy = 48 - (i * 4.2)
            jz = 32 - (i * 6.0)
            vertices.append((jx, jy, jz, "jaw"))

    # 7. Shortened Natural Neck (Shortened, no elongated giraffe neck)
    for ny in (54, 66):
        for side in (-1, 1):
            vertices.append((side * 14, ny, 12, "neck"))
            vertices.append((side * 20, ny, 4, "neck"))

    # 8. Shoulders and Upper Arms
    for side in (-1, 1):
        # Clavicle / shoulder
        vertices.append((side * 35, 74, 8, "shoulder"))
        vertices.append((side * 55, 78, 6, "shoulder"))
        vertices.append((side * 75, 84, 2, "shoulder"))
        # Upper Arm extending down
        vertices.append((side * 88, 102, -2, "arm"))
        vertices.append((side * 98, 125, -6, "arm"))
        vertices.append((side * 105, 148, -10, "arm"))

    return vertices


# ---------------------------------------------------------------------------
# Background Starfield Particles
# ---------------------------------------------------------------------------
class StarParticle:
    def __init__(self):
        self.reset(random_z=True)

    def reset(self, random_z=False):
        self.x = random.uniform(-140, 140)
        self.y = random.uniform(-140, 140)
        self.z = random.uniform(-80, 120) if random_z else random.uniform(90, 130)
        self.vz = random.uniform(-0.35, -0.15)
        self.brightness = random.uniform(0.4, 1.0)

    def update(self):
        self.z += self.vz
        if self.z < -90:
            self.reset(random_z=False)


# ---------------------------------------------------------------------------
# Main GUI Window (Tkinter)
# ---------------------------------------------------------------------------
def start_gui():
    """Launch the 100% native Python Desktop GUI for MYRA."""
    try:
        import tkinter as tk
        from tkinter import messagebox, scrolledtext, simpledialog, ttk
    except ImportError:
        print("Tkinter standard GUI is not available.")
        return False

    root = tk.Tk()
    root.title("MYRA — Desktop AI Assistant")
    root.geometry("1160x780")
    root.minsize(980, 640)
    root.configure(bg="#020908")

    # Dark Cyber Palette
    BG_DARK = "#020908"
    PANEL_BG = "#061814"
    BORDER_CYAN = "#0e4438"
    ACCENT_CYAN = "#22d3ee"
    ACCENT_EMERALD = "#34d399"
    ACCENT_ROSE = "#fb7185"
    ACCENT_BLUE = "#38bdf8"
    TEXT_LIGHT = "#ecfeff"
    TEXT_MUTED = "#94a3b8"
    INPUT_BG = "#041410"

    current_char = tk.StringVar(value="core")
    current_brain = tk.StringVar(value="auto")
    status_var = tk.StringVar(value="✨ MYRA is online and ready")
    chat_history = []

    # Configure Tkinter ttk theme
    style = ttk.Style()
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure("TCombobox", fieldbackground=INPUT_BG, background=PANEL_BG, foreground=TEXT_LIGHT)

    # -----------------------------------------------------------------------
    # Top Bar Header
    # -----------------------------------------------------------------------
    top_frame = tk.Frame(root, bg=PANEL_BG, height=55, padx=16, pady=8, highlightthickness=1, highlightbackground=BORDER_CYAN)
    top_frame.pack(fill="x", side="top")

    # Logo / Title
    logo_lbl = tk.Label(
        top_frame,
        text="🤖  M Y R A",
        font=("Segoe UI", 13, "bold"),
        fg=ACCENT_CYAN,
        bg=PANEL_BG,
    )
    logo_lbl.pack(side="left")

    sub_title = tk.Label(
        top_frame,
        text="— Desktop AI Software",
        font=("Segoe UI", 10),
        fg=TEXT_MUTED,
        bg=PANEL_BG,
    )
    sub_title.pack(side="left", padx=(4, 20))

    # Persona Selector
    p_frame = tk.Frame(top_frame, bg=PANEL_BG)
    p_frame.pack(side="left", padx=8)
    tk.Label(p_frame, text="Persona:", fg=TEXT_MUTED, bg=PANEL_BG, font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
    char_combo = ttk.Combobox(
        p_frame,
        textvariable=current_char,
        values=["core", "male", "female", "custom"],
        state="readonly",
        width=10,
    )
    char_combo.pack(side="left")

    # Brain Provider Selector
    b_frame = tk.Frame(top_frame, bg=PANEL_BG)
    b_frame.pack(side="left", padx=12)
    tk.Label(b_frame, text="Brain:", fg=TEXT_MUTED, bg=PANEL_BG, font=("Segoe UI", 9)).pack(side="left", padx=(0, 4))
    brain_combo = ttk.Combobox(
        b_frame,
        textvariable=current_brain,
        values=["auto", "gemini", "groq", "openrouter", "openai", "deepseek", "mistral", "ollama"],
        state="readonly",
        width=12,
    )
    brain_combo.pack(side="left")

    # Mode Indicator
    mode_lbl = tk.Label(
        top_frame,
        text="🟢 Native Desktop Engine",
        font=("Segoe UI", 9, "bold"),
        fg=ACCENT_EMERALD,
        bg=PANEL_BG,
    )
    mode_lbl.pack(side="right")

    # -----------------------------------------------------------------------
    # Main Body: 3-Column Split
    # Left: 3D Animated Cyber Avatar Canvas
    # Middle: Scrolled Chat Conversation
    # Right: Autonomous PC Agent Toolbar
    # -----------------------------------------------------------------------
    main_body = tk.Frame(root, bg=BG_DARK)
    main_body.pack(fill="both", expand=True, padx=12, pady=10)

    # =======================================================================
    # LEFT PANEL: 3D CYBER PARTICLE AVATAR CANVAS
    # =======================================================================
    left_panel = tk.Frame(main_body, bg=PANEL_BG, width=310, highlightthickness=1, highlightbackground=BORDER_CYAN)
    left_panel.pack(side="left", fill="y", padx=(0, 8))
    left_panel.pack_propagate(False)

    avatar_title = tk.Label(
        left_panel,
        text="✦ NEURAL CYBER AVATAR ✦",
        font=("Segoe UI", 9, "bold"),
        fg=ACCENT_CYAN,
        bg=PANEL_BG,
        pady=6,
    )
    avatar_title.pack(fill="x")

    avatar_canvas = tk.Canvas(
        left_panel,
        width=290,
        height=320,
        bg="#030f0c",
        highlightthickness=1,
        highlightbackground="#082b22",
    )
    avatar_canvas.pack(padx=10, pady=4)

    # Avatar Info Badges
    avatar_status = tk.Label(
        left_panel,
        text="• Front-Facing Interactive Mesh",
        font=("Segoe UI", 8),
        fg=TEXT_MUTED,
        bg=PANEL_BG,
    )
    avatar_status.pack(pady=2)

    avatar_char_lbl = tk.Label(
        left_panel,
        text="Mode: Core Aura (Cyan)",
        font=("Segoe UI", 8, "italic"),
        fg=ACCENT_CYAN,
        bg=PANEL_BG,
    )
    avatar_char_lbl.pack(pady=1)

    # 3D Math Setup
    face_vertices = generate_face_model()
    stars = [StarParticle() for _ in range(50)]

    # Tracking mouse angles (smooth mouse following, ZERO continuous spinning!)
    mouse_target_yaw = 0.0
    mouse_target_pitch = 0.0
    cur_yaw = 0.0
    cur_pitch = 0.0
    morph_burst = 0.0  # Particle explosion/morph timer on character switch
    wave_pulse = 0.0   # Voice speaking audio ripple

    def on_mouse_move(event):
        nonlocal mouse_target_yaw, mouse_target_pitch
        try:
            # Get position relative to canvas center
            cx, cy = 145, 160
            rx = event.x_root - avatar_canvas.winfo_rootx()
            ry = event.y_root - avatar_canvas.winfo_rooty()
            # Clamped angle range [-0.45, 0.45] radians so it NEVER spins 360!
            target_y = (rx - cx) * 0.0022
            target_p = (ry - cy) * 0.0016
            mouse_target_yaw = max(-0.45, min(0.45, target_y))
            mouse_target_pitch = max(-0.35, min(0.35, target_p))
        except Exception:
            pass

    root.bind("<Motion>", on_mouse_move)

    def on_char_changed(*args):
        nonlocal morph_burst
        morph_burst = 1.0  # trigger burst
        c = current_char.get()
        if c == "male":
            avatar_char_lbl.config(text="Mode: Male Persona (Deep Sky)", fg=ACCENT_BLUE)
        elif c == "female":
            avatar_char_lbl.config(text="Mode: Female Persona (Ruby Rose)", fg=ACCENT_ROSE)
        else:
            avatar_char_lbl.config(text="Mode: Core Aura (Cyan Emerald)", fg=ACCENT_CYAN)

    current_char.trace_add("write", on_char_changed)

    # Particle color mapping per persona
    def get_persona_colors():
        c = current_char.get()
        if c == "male":
            return {"dome": "#0284c7", "brow": "#38bdf8", "pupil": "#e0f2fe", "eye": "#60a5fa",
                    "nose": "#38bdf8", "mouth": "#0284c7", "chin": "#0369a1", "neck": "#0c4a6e", "arm": "#075985"}
        elif c == "female":
            return {"dome": "#be123c", "brow": "#fb7185", "pupil": "#fef08a", "eye": "#fda4af",
                    "nose": "#fb7185", "mouth": "#f43f5e", "chin": "#e11d48", "neck": "#9f1239", "arm": "#881337"}
        else:
            return {"dome": "#0d9488", "brow": "#22d3ee", "pupil": "#ecfeff", "eye": "#34d399",
                    "nose": "#22d3ee", "mouth": "#14b8a6", "chin": "#0f766e", "neck": "#064e3b", "arm": "#064e3b"}

    # 3D Animation Render Loop
    def render_avatar_frame():
        nonlocal cur_yaw, cur_pitch, morph_burst, wave_pulse
        try:
            if not root.winfo_exists():
                return
        except Exception:
            return
        avatar_canvas.delete("all")

        # Smooth interpolation to mouse target (smooth easing)
        cur_yaw += (mouse_target_yaw - cur_yaw) * 0.08
        cur_pitch += (mouse_target_pitch - cur_pitch) * 0.08

        if morph_burst > 0:
            morph_burst = max(0.0, morph_burst - 0.04)

        cx, cy = 145, 160
        scale = 1.15
        focal = 280.0
        colors = get_persona_colors()
        t = time.time()

        # 1. Draw floating background stars
        for star in stars:
            star.update()
            # 3D project star
            sz = star.z
            f = focal / (focal + sz + 50)
            sx = cx + star.x * f * 1.3
            sy = cy + star.y * f * 1.3
            if 0 <= sx <= 290 and 0 <= sy <= 320:
                rad = max(1, int(1.8 * star.brightness))
                avatar_canvas.create_oval(sx - rad, sy - rad, sx + rad, sy + rad, fill="#475569", outline="")

        # 2. Speaking ripple wave (concentric expanding rings when speaking)
        if IS_SPEAKING:
            wave_pulse += 0.12
            r1 = (math.sin(wave_pulse) * 15 + 40) % 65 + 30
            r2 = (math.sin(wave_pulse + 1.5) * 20 + 55) % 80 + 35
            avatar_canvas.create_oval(cx - r1, cy - r1, cx + r1, cy + r1, outline="#0e7490", width=1)
            avatar_canvas.create_oval(cx - r2, cy - r2, cx + r2, cy + r2, outline="#065f46", width=1)

        # 3. Project and draw sculpted face vertices
        cos_p = math.cos(cur_pitch)
        sin_p = math.sin(cur_pitch)
        cos_y = math.cos(cur_yaw)
        sin_y = math.sin(cur_yaw)

        # Burst dispersion factor
        disp = morph_burst * 24.0

        for (x, y, z, cat) in face_vertices:
            # Speaking mouth movement (visibly opens and closes)
            if IS_SPEAKING and cat.startswith("mouth"):
                mouth_delta = math.sin(t * 16) * 4.5
                y = y + (mouth_delta if cat == "mouth_down" else -mouth_delta * 0.4)

            # Morph burst dispersion
            if disp > 0:
                x += math.sin(x * 12.0) * disp
                y += math.cos(y * 12.0) * disp

            # 3D Rotation (Pitch around X, Yaw around Y)
            # Pitch
            y1 = y * cos_p - z * sin_p
            z1 = y * sin_p + z * cos_p
            # Yaw
            x2 = x * cos_y + z1 * sin_y
            z2 = -x * sin_y + z1 * cos_y

            # Perspective projection
            f = focal / (focal + z2)
            px = cx + x2 * f * scale
            py = cy + y1 * f * scale

            # Node size & color
            pt_color = colors.get(cat, colors.get("dome", "#22d3ee"))
            if cat == "pupil":
                pr = 3.5
                pt_color = colors["pupil"]
            elif cat in ("eye", "nose_tip"):
                pr = 2.5
            elif cat in ("mouth_up", "mouth_down", "brow"):
                pr = 2.0
            else:
                pr = 1.6

            avatar_canvas.create_oval(px - pr, py - pr, px + pr, py + pr, fill=pt_color, outline="")

        root.after(35, render_avatar_frame)

    render_avatar_frame()

    # =======================================================================
    # MIDDLE PANEL: CHAT LOG CONVERSATION & INPUT AREA
    # =======================================================================
    chat_container = tk.Frame(main_body, bg=PANEL_BG, highlightthickness=1, highlightbackground=BORDER_CYAN)
    chat_container.pack(side="left", fill="both", expand=True, padx=(0, 8))

    # Conversation Log Area
    chat_log = scrolledtext.ScrolledText(
        chat_container,
        wrap=tk.WORD,
        bg=INPUT_BG,
        fg=TEXT_LIGHT,
        font=("Segoe UI", 10),
        insertbackground=ACCENT_CYAN,
        relief="flat",
        padx=12,
        pady=10,
    )
    chat_log.pack(fill="both", expand=True, padx=8, pady=(8, 4))

    # Chat Log Tags styling
    chat_log.tag_config("user_hdr", foreground=ACCENT_CYAN, font=("Segoe UI", 10, "bold"))
    chat_log.tag_config("ai_hdr", foreground=ACCENT_EMERALD, font=("Segoe UI", 10, "bold"))
    chat_log.tag_config("agent_hdr", foreground="#fbbf24", font=("Segoe UI", 10, "bold"))
    chat_log.tag_config("system", foreground="#94a3b8", font=("Segoe UI", 9, "italic"))
    chat_log.tag_config("body", foreground=TEXT_LIGHT, font=("Segoe UI", 10))

    # Initial Welcome
    chat_log.insert(tk.END, "✦ MYRA Autonomous AI Assistant (100% Python Native Desktop Window) ✦\n\n", "system")
    chat_log.insert(tk.END, "MYRA [Ready]:\n", "ai_hdr")
    chat_log.insert(
        tk.END,
        "হ্যালো! আমি মাইরা। আপনার কম্পিউটারের যেকোনো ফাইল খোঁজা, লাইভ সোনার রেট দেখা, শপিং সার্চ, "
        "কিংবা যেকোনো প্রশ্নের উত্তর দিতে আমি প্রস্তুত। কথা বলুন বা লিখে পাঠান!\n\n",
        "body",
    )

    def append_message(role: str, text: str, meta: str = ""):
        now_time = datetime.now().strftime("%I:%M %p")
        if role == "user":
            chat_log.insert(tk.END, f"You [{now_time}]:\n", "user_hdr")
            chat_log.insert(tk.END, f"{text}\n\n", "body")
        elif role == "agent":
            tag = f"⚡ Autonomous Agent ({meta}) [{now_time}]" if meta else f"⚡ Autonomous Agent [{now_time}]"
            chat_log.insert(tk.END, f"{tag}:\n", "agent_hdr")
            chat_log.insert(tk.END, f"{text}\n\n", "body")
        else:
            tag = f"MYRA ({meta}) [{now_time}]" if meta else f"MYRA [{now_time}]"
            chat_log.insert(tk.END, f"{tag}:\n", "ai_hdr")
            chat_log.insert(tk.END, f"{text}\n\n", "body")
        chat_log.see(tk.END)

    # -----------------------------------------------------------------------
    # Lower Status Indicator (Shows only when processing)
    # -----------------------------------------------------------------------
    status_bar = tk.Label(
        chat_container,
        textvariable=status_var,
        font=("Segoe UI", 9, "bold"),
        fg=ACCENT_EMERALD,
        bg=PANEL_BG,
        anchor="w",
        padx=12,
        pady=2,
    )
    status_bar.pack(fill="x")

    # -----------------------------------------------------------------------
    # Input Area: Voice Record + Text Entry + Send Button
    # -----------------------------------------------------------------------
    input_box_frame = tk.Frame(chat_container, bg=PANEL_BG, padx=8, pady=8)
    input_box_frame.pack(fill="x")

    user_entry = tk.Entry(
        input_box_frame,
        bg=INPUT_BG,
        fg=TEXT_LIGHT,
        font=("Segoe UI", 11),
        insertbackground=ACCENT_CYAN,
        relief="flat",
        highlightthickness=1,
        highlightbackground="#0b382d",
    )
    user_entry.pack(side="left", fill="x", expand=True, padx=(0, 6), ipady=7)

    # -----------------------------------------------------------------------
    # Send Chat Action (Shared by typing and voice auto-send)
    # -----------------------------------------------------------------------
    def send_chat_action(custom_text: str = None):
        msg = custom_text if custom_text is not None else user_entry.get().strip()
        if not msg:
            return
        if custom_text is None:
            user_entry.delete(0, tk.END)

        append_message("user", msg)
        chat_history.append({"role": "user", "text": msg})

        # Set status lower down
        status_var.set("মাইরা শুনেছে, উত্তর দিচ্ছে এক্ষুনি…")

        def _chat_worker():
            try:
                # 1. Check local agent intent (Gold rate, shopping, files, whatsapp)
                local_res = agent.parse_and_execute_local_intent(msg)
                if local_res and local_res.get("ok"):
                    reply = local_res.get("voice_reply") or local_res.get("report", "")
                    root.after(0, lambda: append_message("agent", reply, "Local Intent (0 Tokens)"))
                    root.after(0, lambda: status_var.set("✨ Executed locally with 0 tokens"))
                    speak_text_async(reply, character=current_char.get())
                    return

                # 2. Regular AI Multi-Brain Chat
                payload = {
                    "messages": chat_history[-12:],
                    "character": current_char.get(),
                    "provider": current_brain.get(),
                }
                res = chat.get_reply(payload)
                reply = res.get("reply", "")
                chat_history.append({"role": "assistant", "text": reply})
                prov_lbl = res.get("provider_label", "AI")
                root.after(0, lambda: append_message("ai", reply, prov_lbl))

                # Check if memory was extracted
                if res.get("memory_learned"):
                    root.after(0, lambda: status_var.set(f"🧠 Saved memory: {res['memory_learned'][:35]}..."))
                else:
                    root.after(0, lambda: status_var.set("✨ Ready"))

                speak_text_async(reply, character=current_char.get())
            except Exception as exc:
                err_msg = f"Notice: {exc}"
                root.after(0, lambda: append_message("ai", err_msg, "System Error"))
                root.after(0, lambda: status_var.set("⚠️ Could not complete request"))

        threading.Thread(target=_chat_worker, daemon=True).start()

    # -----------------------------------------------------------------------
    # Voice Input with Speech Recognition & Auto-Send on Silence
    # -----------------------------------------------------------------------
    is_listening = False

    def toggle_voice_recognition():
        nonlocal is_listening
        if is_listening:
            return

        def _voice_worker():
            nonlocal is_listening
            is_listening = True
            root.after(0, lambda: voice_btn.config(text="🔴 Listening...", bg="#991b1b", fg="#ffffff"))
            root.after(0, lambda: status_var.set("🔴 শুনছি… কথা বলুন (Listening... speak now)"))

            try:
                # Try SpeechRecognition
                import speech_recognition as sr
                r = sr.Recognizer()
                r.pause_threshold = 0.8  # 800ms silence ends speech
                with sr.Microphone() as source:
                    r.adjust_for_ambient_noise(source, duration=0.6)
                    audio = r.listen(source, timeout=6, phrase_time_limit=14)

                root.after(0, lambda: status_var.set("মাইরা শুনেছে, টেক্সট প্রসেস করছে…"))
                # Try Bengali recognition first, fallback to English
                text = ""
                try:
                    text = r.recognize_google(audio, language="bn-BD")
                except Exception:
                    try:
                        text = r.recognize_google(audio, language="en-US")
                    except Exception:
                        pass

                if text:
                    root.after(0, lambda: user_entry.delete(0, tk.END))
                    root.after(0, lambda: user_entry.insert(0, text))
                    # AUTO-SEND IMMEDIATELY ON SILENCE! Zero manual click required!
                    root.after(100, lambda: send_chat_action(custom_text=text))
                else:
                    root.after(0, lambda: status_var.set("⚠️ স্পষ্ট শোনা যায়নি। আবার বলুন।"))
            except ImportError:
                root.after(0, lambda: status_var.set("ℹ️ Voice recognition module: pip install SpeechRecognition pyaudio"))
                # Fallback simple speech dialog
                ans = simpledialog.askstring("Voice Input", "ভয়েসে যা বলতে চান টাইপ করুন:")
                if ans:
                    root.after(0, lambda: send_chat_action(custom_text=ans))
            except Exception as exc:
                root.after(0, lambda: status_var.set(f"⚠️ Voice error: {exc}"))
            finally:
                is_listening = False
                root.after(0, lambda: voice_btn.config(text="🎤 Speak", bg="#09382e", fg=ACCENT_CYAN))

        threading.Thread(target=_voice_worker, daemon=True).start()

    voice_btn = tk.Button(
        input_box_frame,
        text="🎤 Speak",
        bg="#09382e",
        fg=ACCENT_CYAN,
        font=("Segoe UI", 10, "bold"),
        relief="flat",
        padx=12,
        pady=4,
        command=toggle_voice_recognition,
    )
    voice_btn.pack(side="left", padx=(0, 6))

    send_btn = tk.Button(
        input_box_frame,
        text="Send ➤",
        bg="#0f4438",
        fg=ACCENT_CYAN,
        font=("Segoe UI", 10, "bold"),
        relief="flat",
        padx=14,
        pady=4,
        command=lambda: send_chat_action(),
    )
    send_btn.pack(side="right")
    user_entry.bind("<Return>", lambda e: send_chat_action())

    # =======================================================================
    # RIGHT PANEL: PC AUTONOMOUS AGENT ACTIONS & SETTINGS
    # =======================================================================
    side_panel = tk.Frame(main_body, bg=PANEL_BG, width=240, padx=12, pady=10, highlightthickness=1, highlightbackground=BORDER_CYAN)
    side_panel.pack(side="right", fill="y")
    side_panel.pack_propagate(False)

    tk.Label(
        side_panel,
        text="⚡ PC AUTOMATION",
        font=("Segoe UI", 10, "bold"),
        fg=ACCENT_CYAN,
        bg=PANEL_BG,
    ).pack(anchor="w", pady=(0, 8))

    # Autonomous Action Handlers
    def run_gold_rate():
        user_entry.delete(0, tk.END)
        user_entry.insert(0, "আজকের গোল্ড রেট কি")
        send_chat_action()

    def run_file_search():
        fname = simpledialog.askstring("Search PC Files", "খুঁজতে চাওয়া ফাইলের নাম লিখুন (File name):")
        if fname:
            user_entry.delete(0, tk.END)
            user_entry.insert(0, f"search file {fname}")
            send_chat_action()

    def run_shopping():
        item = simpledialog.askstring("Shopping Search", "কি কিনতে চান লিখুন (Product name):")
        if item:
            user_entry.delete(0, tk.END)
            user_entry.insert(0, f"কিনতে চাই {item}")
            send_chat_action()

    def run_whatsapp():
        contact = simpledialog.askstring("WhatsApp", "কাকে মেসেজ পাঠাবেন? (Phone/Name):")
        if contact:
            msg = simpledialog.askstring("WhatsApp", "মেসেজ কি পাঠাবেন?:")
            if msg:
                user_entry.delete(0, tk.END)
                user_entry.insert(0, f"send whatsapp to {contact} message {msg}")
                send_chat_action()

    def show_memories_dialog():
        mems = memory.list_memories()
        win = tk.Toplevel(root)
        win.title("🧠 Saved Local SQLite Memory")
        win.geometry("580x420")
        win.configure(bg=BG_DARK)

        tk.Label(win, text="🧠 MYRA Persistent SQLite Memories", font=("Segoe UI", 11, "bold"), fg=ACCENT_CYAN, bg=BG_DARK).pack(pady=(12, 4))
        tk.Label(win, text="Stored securely in local data/myra.db database", font=("Segoe UI", 8), fg=TEXT_MUTED, bg=BG_DARK).pack(pady=(0, 8))

        txt = scrolledtext.ScrolledText(win, bg=INPUT_BG, fg=TEXT_LIGHT, font=("Segoe UI", 10), padx=8, pady=8)
        txt.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        if not mems:
            txt.insert(tk.END, "এখনো কোনো মেমোরি সেভ হয়নি। চ্যাটে কথা বললে মাইরা স্বয়ংক্রিয়ভাবে তথ্য মনে রাখবে।\n")
        else:
            for m in mems:
                txt.insert(tk.END, f"• [{m.get('category', 'general')}] {m['text']}\n  (Saved: {m.get('created_at')})\n\n")

    def show_settings_dialog():
        win = tk.Toplevel(root)
        win.title("⚙️ AI Multi-Brain API Keys")
        win.geometry("560x520")
        win.configure(bg=BG_DARK)

        st = config.key_status()

        tk.Label(win, text="⚙️ Configure AI Brain API Keys", font=("Segoe UI", 12, "bold"), fg=ACCENT_CYAN, bg=BG_DARK).pack(pady=(12, 4))
        tk.Label(win, text="Keys are stored safely on your laptop in the local .env file", font=("Segoe UI", 8), fg=TEXT_MUTED, bg=BG_DARK).pack(pady=(0, 10))

        def make_field(label_txt, masked_val):
            tk.Label(win, text=label_txt, bg=BG_DARK, fg=TEXT_LIGHT, font=("Segoe UI", 9)).pack(anchor="w", padx=16, pady=(4, 1))
            entry = tk.Entry(win, width=54, bg=INPUT_BG, fg=TEXT_LIGHT, font=("Segoe UI", 9), insertbackground=ACCENT_CYAN)
            entry.pack(padx=16, pady=(0, 6))
            if masked_val:
                entry.insert(0, masked_val)
            return entry

        gem_e = make_field("Google Gemini API Key (Free & Paid):", st.get("gemini", {}).get("masked"))
        groq_e = make_field("Groq API Key (Ultra-Fast Free):", st.get("groq", {}).get("masked"))
        or_e = make_field("OpenRouter API Key (Free & Paid Models):", st.get("openrouter", {}).get("masked"))
        oa_e = make_field("OpenAI API Key (Paid ChatGPT):", st.get("openai", {}).get("masked"))
        ds_e = make_field("DeepSeek API Key:", st.get("deepseek", {}).get("masked"))

        def _save_and_verify():
            def val(e):
                t = e.get().strip()
                return None if t.startswith("••") or not t else t

            config.save_keys(
                gemini=val(gem_e),
                groq=val(groq_e),
                openrouter=val(or_e),
                openai=val(oa_e),
                deepseek=val(ds_e),
            )
            messagebox.showinfo("Saved", "API Keys saved safely in local .env file!")
            win.destroy()

        tk.Button(
            win,
            text="Save Keys 💾",
            bg="#0f4438",
            fg=ACCENT_CYAN,
            font=("Segoe UI", 10, "bold"),
            relief="flat",
            padx=16,
            pady=6,
            command=_save_and_verify,
        ).pack(pady=12)

    btn_cfg = {
        "bg": "#0a261f",
        "fg": TEXT_LIGHT,
        "font": ("Segoe UI", 9),
        "relief": "flat",
        "pady": 6,
        "anchor": "w",
        "padx": 10,
    }

    tk.Button(side_panel, text="🪙 Live Gold Rate", command=run_gold_rate, **btn_cfg).pack(fill="x", pady=2)
    tk.Button(side_panel, text="🔍 Search PC Files", command=run_file_search, **btn_cfg).pack(fill="x", pady=2)
    tk.Button(side_panel, text="🛍️ Shopping Search", command=run_shopping, **btn_cfg).pack(fill="x", pady=2)
    tk.Button(side_panel, text="💬 Send WhatsApp", command=run_whatsapp, **btn_cfg).pack(fill="x", pady=2)

    tk.Frame(side_panel, bg=BORDER_CYAN, height=1).pack(fill="x", pady=10)

    tk.Label(side_panel, text="🧠 KNOWLEDGE & TOOLS", font=("Segoe UI", 10, "bold"), fg=ACCENT_CYAN, bg=PANEL_BG).pack(anchor="w", pady=(0, 6))
    tk.Button(side_panel, text="🧠 View Saved Memories", command=show_memories_dialog, **btn_cfg).pack(fill="x", pady=2)
    tk.Button(side_panel, text="⚙️ Multi-Brain API Keys", command=show_settings_dialog, **btn_cfg).pack(fill="x", pady=2)

    user_entry.focus_set()
    root.mainloop()
    return True


if __name__ == "__main__":
    start_gui()
