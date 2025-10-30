#!/usr/bin/env python3
import json, time, random, threading, socket, os, select, subprocess
from pathlib import Path
from demo_opts import get_device
from PIL import Image

CONFIG_PATH = Path(__file__).with_name("rebecca.json")
XP_STORE = Path(__file__).with_name("rebecca_xp.json")
SOCKET_PATH = "/tmp/rebecca.sock"

# ---------------- first-run name setup -----------------
def ensure_name(cfg_path):
    cfg_data = load_json(cfg_path, {})

    name_data = cfg_data.get("name", {})
    if not name_data.get("firstname"):
        # Check if running interactively
        if os.isatty(0):  # stdin is a terminal
            firstname = input("Enter the character's first name: ").strip()
        else:
            firstname = "Rebecca"  # default for headless

        if not firstname:
            firstname = "Rebecca"  # fallback

        cfg_data["name"] = {"firstname": firstname}
        save_json(cfg_path, cfg_data)
        print(f"✅ Saved name '{firstname}' to {cfg_path}")

    return cfg_data
    
# ---------------- helpers -----------------
def load_json(p, default):
    if p.exists():
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError:
            print(f"⚠️ JSON decode error in {p}, using default")
            return default
    return default

def save_json(p, data):
    p.write_text(json.dumps(data, indent=2))

# Ensure mood key exists in xp store
xp_data = load_json(XP_STORE, {"xp": 0, "level": 0, "mood": "Happy"})
if "mood" not in xp_data:
    xp_data["mood"] = "Happy"
    save_json(XP_STORE, xp_data)

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

        # fallback for images_dir
        images_dir = cfg.get("images_dir")
        if not images_dir:
            images_dir = os.path.join(os.path.dirname(__file__), "oLed/rebecca/faces_rebecca")
            print(f"⚠️ 'images_dir' missing in config, using fallback: {images_dir}")

        self.device = device
        self.display = Display(device, images_dir)

        self.state = "LOOK_AROUND"
        self.running = True
        self.xpdata = load_json(XP_STORE, {"xp":0,"level":0, "mood": "Happy"})
        self.last_xp_tick = time.time()
        self.last_input = time.time()
        self.state_start = time.time()  # track state start

    def set_state(self, new_state):
        if new_state != self.state:
            self.state = new_state
            self.state_start = time.time()
            print(f"State → {new_state}")

    def add_xp(self, n):
        self.xpdata["xp"] += n
        lvls = self.cfg.get("leveling", {}).get("levels", [0,50,150,350,700,1200])
        lvl = self.xpdata.get("level", 0)
        for i, t in enumerate(lvls):
            if self.xpdata["xp"] >= t:
                lvl = i
        if lvl > self.xpdata.get("level", 0):
            self.xpdata["level"] = lvl
            print(f"🎉 LEVEL UP! {lvl}")
            self.set_state("LEVELUP")
        save_json(XP_STORE, self.xpdata)

    def event(self, name):
        emap = self.cfg.get("event_map", {})
        if name in emap:
            self.set_state(emap[name])
            print(f"Event: {name} → {self.state}")
        if name == "rfid_scan":
            xp_for_rfid = self.cfg.get("leveling", {}).get("xp_for_rfid", 1)
            self.add_xp(xp_for_rfid)
        if name in ("user_return", "screensaver_off"):
            self.add_xp(1)
        self.last_input = time.time()

    def run(self):
        while self.running:
            # passive XP
            if time.time() - self.last_xp_tick > 60:
                xp_per_min = self.cfg.get("leveling", {}).get("xp_per_minute_running", 1)
                self.add_xp(xp_per_min)
                self.last_xp_tick = time.time()

            # idle detection fallback
            if time.time() - self.last_input > 60*5:
                idle_long_state = self.cfg.get("event_map", {}).get("idle_long","SAD")
                self.set_state(idle_long_state)

            sconf = self.cfg.get("states", {}).get(self.state, {})
            t = sconf.get("type", "idle_animation")
            state_name = self.state

            rti = sconf.get("return_to_idle_after")
            if rti and time.time() - self.state_start > rti:
                self.set_state("LOOK_AROUND")
                continue

            if t == "idle_animation":
                frames = sconf.get("frames", [])
                if frames:
                    f = random.choice(frames)
                    if random.random() < sconf.get("happy_chance", 0.2):
                        happy = [x for x in frames if "HAPPY" in x]
                        if happy: f = random.choice(happy)
                    img = self.display.load(f)
                    self.display.show(img)
                    time.sleep(random.uniform(sconf.get("min_delay",0.5), sconf.get("max_delay",1.5)))
            elif t == "static":
                img = self.display.load(sconf.get("frame"))
                self.display.show(img)
                time.sleep(sconf.get("delay",2.0))
            elif t == "static_cycle":
                delay = sconf.get("delay", 2.0)
                while self.state == state_name:
                    for f in sconf.get("frames", []):
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

# ---------------- idle/screensaver monitor 🆕 -----------------
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
    cfg = ensure_name(CONFIG_PATH)
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
