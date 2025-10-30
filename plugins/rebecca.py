#!/usr/bin/env python3
import json, time, random, threading, socket, os, select, subprocess
from pathlib import Path
from demo_opts import get_device
from PIL import Image

CONFIG_PATH = Path(__file__).with_name("rebecca.json")
XP_STORE = Path(__file__).with_name("rebecca_xp.json")
SOCKET_PATH = "/tmp/rebecca.sock"

# ---------------- helpers -----------------
def load_json(p, default):
    """Load JSON from file; return default if file missing or invalid."""
    if p.exists():
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError as e:
            print(f"⚠️ Warning: Invalid JSON in {p.name}, using default. Error: {e}")
            return default
    return default

def save_json(p, data):
    """Save JSON to file with indent=2."""
    p.write_text(json.dumps(data, indent=2))

def validate_rebecca_json(data):
    """Ensure required keys exist in rebecca.json"""
    changed = False
    if "name" not in data:
        data["name"] = {"firstname": "Rebecca"}
        changed = True
    if "levels" not in data:
        data["levels"] = [0, 50, 150, 350, 700, 1200]
        changed = True
    return changed, data

def validate_rebecca_xp_json(data):
    """Ensure required keys exist in rebecca_xp.json"""
    changed = False
    if "xp" not in data:
        data["xp"] = 0
        changed = True
    if "level" not in data:
        data["level"] = 0
        changed = True
    if "mood" not in data:
        data["mood"] = "Happy"
        changed = True
    return changed, data

# ---------------- display -----------------
class Display:
    def __init__(self, device, base):
        self.device = device
        self.base = Path(base)
        self.cache = {}
        self.bg = Image.new("RGBA", device.size, "white")

    def load(self, f):
        p = self.base / f
        if f not in self.cache:
            self.cache[f] = Image.open(p).convert("RGBA")
        return self.cache[f]

    def show(self, img):
        frame = self.bg.copy()
        pos = ((self.device.width - img.width)//2, 0)
        frame.paste(img, pos, img)
        self.device.display(frame.convert(self.device.mode))

# ---------------- state machine -----------
class Rebecca(threading.Thread):
    def __init__(self, device, cfg):
        super().__init__(daemon=True)
        self.cfg = cfg
        self.device = device
        self.display = Display(device, cfg["images_dir"])
        self.state = "LOOK_AROUND"
        self.running = True
        self.last_xp_tick = time.time()
        self.last_input = time.time()
        self.state_start = time.time()  # track state start

        # ---------------- JSON loading & validation ----------------
        # rebecca.json
        self.rebecca_data = load_json(CONFIG_PATH, {})
        changed, self.rebecca_data = validate_rebecca_json(self.rebecca_data)
        if changed:
            save_json(CONFIG_PATH, self.rebecca_data)

        # rebecca_xp.json
        self.xpdata = load_json(XP_STORE, {"xp":0, "level":0, "mood":"Happy"})
        changed, self.xpdata = validate_rebecca_xp_json(self.xpdata)
        if changed:
            save_json(XP_STORE, self.xpdata)

    def set_state(self, new_state):
        """Switch state and store start time"""
        if new_state != self.state:
            self.state = new_state
            self.state_start = time.time()
            print(f"State → {new_state}")

    def add_xp(self, n):
        self.xpdata["xp"] += n
        lvls = self.cfg["leveling"]["levels"]
        lvl = self.xpdata["level"]
        for i, t in enumerate(lvls):
            if self.xpdata["xp"] >= t:
                lvl = i
        if lvl > self.xpdata["level"]:
            self.xpdata["level"] = lvl
            print(f"🎉 LEVEL UP! {lvl}")
            self.set_state("LEVELUP")
        save_json(XP_STORE, self.xpdata)

    def event(self, name):
        emap = self.cfg["event_map"]
        if name in emap:
            self.set_state(emap[name])
            print(f"Event: {name} → {self.state}")
        if name == "rfid_scan":
            self.add_xp(self.cfg["leveling"]["xp_for_rfid"])
        if name in ("user_return", "screensaver_off"):
            self.add_xp(1)
        self.last_input = time.time()

    # ---------------- run loop -----------------
    def run(self):
        while self.running:
            # passive XP
            if time.time() - self.last_xp_tick > 60:
                self.add_xp(self.cfg["leveling"]["xp_per_minute_running"])
                self.last_xp_tick = time.time()

            # idle detection
            if time.time() - self.last_input > 60*5:
                self.set_state(self.cfg["event_map"].get("idle_long","SAD"))

            sconf = self.cfg["states"][self.state]
            t = sconf["type"]
            state_name = self.state

            rti = sconf.get("return_to_idle_after")
            if rti and time.time() - self.state_start > rti:
                self.set_state("LOOK_AROUND")
                continue

            if t == "idle_animation":
                frames = sconf["frames"]
                f = random.choice(frames)
                if random.random() < sconf.get("happy_chance", 0.2):
                    happy = [x for x in frames if "HAPPY" in x]
                    if happy: f = random.choice(happy)
                img = self.display.load(f)
                self.display.show(img)
                time.sleep(random.uniform(sconf["min_delay"], sconf["max_delay"]))

            elif t == "static":
                img = self.display.load(sconf["frame"])
                self.display.show(img)
                time.sleep(sconf.get("delay",2.0))

            elif t == "static_cycle":
                delay = sconf.get("delay", 2.0)
                while self.state == state_name:
                    for f in sconf["frames"]:
                        if self.state != state_name:
                            break
                        if rti and time.time() - self.state_start > rti:
                            self.set_state("LOOK_AROUND")
                            break
                        img = self.display.load(f)
                        self.display.show(img)
                        time.sleep(delay)
                    time.sleep(0.05)
            else:
                time.sleep(0.1)

# ---------------- socket listener ----------
class EventListener(threading.Thread):
    def __init__(self, rebecca):
        super().__init__(daemon=True)
        self.rebecca = rebecca
        self.running = True
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        if os.path.exists(SOCKET_PATH):
            os.remove(SOCKET_PATH)
        self.sock.bind(SOCKET_PATH)
        os.chmod(SOCKET_PATH, 0o666)

    def run(self):
        print(f"📡 Listening on {SOCKET_PATH}")
        while self.running:
            r, _, _ = select.select([self.sock], [], [], 0.5)
            if self.sock in r:
                try:
                    data, _ = self.sock.recvfrom(1024)
                    msg = json.loads(data.decode().strip())
                    ev = msg.get("type")
                    if ev:
                        self.rebecca.event(ev)
                except Exception as e:
                    print("socket error:", e)

# ---------------- idle/screensaver monitor -----------------
def idle_monitor(rebecca, check_interval=5):
    active = True
    thresholds = rebecca.cfg.get("idle_thresholds", {})
    short_idle = thresholds.get("short_idle", 30000)
    long_idle = thresholds.get("long_idle", 300000)
    screensaver_idle = thresholds.get("screensaver_idle", 600000)

    while True:
        try:
            idle_ms = int(subprocess.check_output(["xprintidle"]))
            if idle_ms >= screensaver_idle:
                rebecca.event("screensaver_on")
            elif idle_ms >= long_idle:
                rebecca.event("idle_long")
            elif idle_ms >= short_idle:
                rebecca.event("look_around")

            if idle_ms < short_idle and not active:
                rebecca.event("screensaver_off")
                active = True
            elif idle_ms >= short_idle:
                active = False
        except Exception as e:
            print("Idle monitor error:", e)
        time.sleep(check_interval)

# ---------------- main --------------------
if __name__ == "__main__":
    cfg = load_json(CONFIG_PATH, {})
    device = get_device()
    r = Rebecca(device, cfg)
    r.start()

    listener = EventListener(r)
    listener.start()

    threading.Thread(target=idle_monitor, args=(r,), daemon=True).start()

    print("Rebecca running — send JSON events to /tmp/rebecca.sock")
    print('Example: echo \'{"type":"rfid_scan"}\' | socat - UNIX-SENDTO:/tmp/rebecca.sock')
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        r.running = False
        listener.running = False
        print("Bye.")
