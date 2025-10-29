#!/usr/bin/env python3
import json, time, random, threading, socket, os, select
from pathlib import Path
from demo_opts import get_device
from PIL import Image

CONFIG_PATH = Path(__file__).with_name("rebecca.json")
XP_STORE = Path(__file__).with_name("rebecca_xp.json")
SOCKET_PATH = "/tmp/rebecca.sock"

# ---------------- helpers -----------------
def load_json(p, default):
    if p.exists():
        return json.loads(p.read_text())
    return default

def save_json(p, data):
    p.write_text(json.dumps(data, indent=2))

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
        self.xpdata = load_json(XP_STORE, {"xp":0,"level":0})
        self.last_xp_tick = time.time()
        self.last_input = time.time()

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
            self.state = "LEVELUP"
        save_json(XP_STORE, self.xpdata)

    def event(self, name):
        emap = self.cfg["event_map"]
        if name in emap:
            self.state = emap[name]
            print(f"Event: {name} → {self.state}")
        if name == "rfid_scan":
            self.add_xp(self.cfg["leveling"]["xp_for_rfid"])
        if name in ("user_return", "screensaver_off"):
            self.add_xp(1)
        self.last_input = time.time()

    # 🆕 helper to handle return to idle
    def maybe_return_to_idle(self, sconf, state_name):
        if "return_to_idle_after" in sconf:
            end_time = time.time() + sconf["return_to_idle_after"]
            while time.time() < end_time and self.state == state_name:
                time.sleep(0.1)
            if self.state == state_name:
                print(f"⏳ Returning to LOOK_AROUND from {state_name}")
                self.state = "LOOK_AROUND"

    def run(self):
        while self.running:
            # passive XP per minute
            if time.time() - self.last_xp_tick > 60:
                self.add_xp(self.cfg["leveling"]["xp_per_minute_running"])
                self.last_xp_tick = time.time()

            # idle detection
            if time.time() - self.last_input > 60*5:
                self.state = self.cfg["event_map"].get("idle_long","SAD")

            sconf = self.cfg["states"][self.state]
            t = sconf["type"]
            state_name = self.state  # 🆕 store once for reference

            if t == "idle_animation":
                frames = sconf["frames"]
                f = random.choice(frames)
                if random.random() < sconf.get("happy_chance",0.2):
                    happy = [x for x in frames if "HAPPY" in x]
                    if happy: f = random.choice(happy)
                img = self.display.load(f)
                self.display.show(img)
                time.sleep(random.uniform(sconf["min_delay"], sconf["max_delay"]))
                self.maybe_return_to_idle(sconf, state_name)  # 🆕 added

            elif t == "static":
                img = self.display.load(sconf["frame"])
                self.display.show(img)
                time.sleep(sconf.get("delay",2.0))
                self.maybe_return_to_idle(sconf, state_name)  # 🆕 added

            elif t == "static_cycle":
                while self.state == state_name:
                    for f in sconf["frames"]:
                        if self.state != state_name:
                            break
                        img = self.display.load(f)
                        self.display.show(img)
                        time.sleep(sconf.get("delay", 2.0))
                    self.maybe_return_to_idle(sconf, state_name)  # 🆕 added

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

# ---------------- main --------------------
if __name__ == "__main__":
    cfg = load_json(CONFIG_PATH, {})
    device = get_device()
    r = Rebecca(device, cfg)
    r.start()

    listener = EventListener(r)
    listener.start()

    print("Rebecca running — send JSON events to /tmp/rebecca.sock")
    print('Example: echo \'{"type":"rfid_scan"}\' | socat - UNIX-SENDTO:/tmp/rebecca.sock')
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        r.running = False
        listener.running = False
        print("Bye.")
