```markdown
# Kali_touch (launcher for Kali touchscreen)

This is a small launcher UI for Kali Linux with touchscreen support.
Target environment: Raspberry Pi running Kali Linux under X11.

Quick start (Raspberry Pi / Kali Linux on X11)
1. Install system packages (for focusing windows):
   sudo apt update
   sudo apt install -y xdotool wmctrl

2. Create a virtualenv and install Python deps:
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt

3. Provide an `apps.json` file (see `apps.example.json`) with your apps.

4. Run:
   python3 launcher.py

Notes
- On Wayland these window-focus helpers (xdotool/wmctrl) will not work reliably.
- You can add a `focus_command` per app in apps.json if the window requires a custom activation command:
  { "name": { "cmd": "firefox", "focus_command": "wmctrl -a 'Firefox'"}}
- The launcher will try to terminate the launched app by killing its process group; avoid using broad pkill rules in the code.

If you want me to push other changes, tell me whether to create a branch + PR or commit directly to main.
```