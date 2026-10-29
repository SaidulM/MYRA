"""Build MYRA-Preview.html from ui/index.html, style, Three.js and app.js."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = ROOT / "ui"
html = (UI / "index.html").read_text(encoding="utf-8")
css = (UI / "style.css").read_text(encoding="utf-8")
three = (UI / "vendor" / "three.min.js").read_text(encoding="utf-8")
qrcode_path = UI / "vendor" / "qrcode.min.js"
qrcode = qrcode_path.read_text(encoding="utf-8") if qrcode_path.exists() else ""
app = (UI / "app.js").read_text(encoding="utf-8")

for label, content in (("Three.js", three), ("QRCode", qrcode), ("app.js", app)):
    if "</script" in content.lower():
        raise SystemExit(f"Cannot safely inline {label}: it contains a closing script tag")

html = html.replace('<link rel="stylesheet" href="style.css">', "<style>\n" + css + "\n</style>")
html = html.replace('<script src="vendor/three.min.js"></script>', "<script>\n" + three + "\n</script>")
if qrcode:
    html = html.replace('<script src="vendor/qrcode.min.js"></script>', "<script>\n" + qrcode + "\n</script>")
html = html.replace('<script src="app.js"></script>', "<script>\n" + app + "\n</script>")
header = (
    "<!-- MYRA — one-file UI preview (Core 2.0 foundation). "
    "Real persistent chat, Agent skills, vision and key-saving require the local Python backend; "
    "run MYRA.bat/start.bat or run_desktop.py on your own laptop. -->\n"
)
(ROOT / "MYRA-Preview.html").write_text(header + html, encoding="utf-8")
print(ROOT / "MYRA-Preview.html")
