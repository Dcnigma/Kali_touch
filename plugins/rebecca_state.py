#!/usr/bin/env python3
import json, time, random, threading
from pathlib import Path
from demo_opts import get_device
from PIL import Image

CONFIG_PATH = Path(__file__).with_name("rebecca.json")
XP_STORE = Path(__file__).with_name("rebecca_xp.json")

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
        for i,t in enumerate(lvls):
            if self.xpdata["xp"] >= t:
                lvl = i
        if lvl > self.xpdata["level"]:
            self.xpdata["level"] = lvl
            print(f"LEVEL UP! {lvl}")
            self.state = "LEVELUP"
        save_json(XP_STORE, self.xpdata)

    def event(self, name):
        emap = self.cfg["event_map"]
        if name in emap:
            self.state = emap[name]
        if name == "rfid_scan":
            self.add_xp(self.cfg["leveling"]["xp_for_rfid"])
        if name in ("user_return","screensaver_off"):
            self.add_xp(1)
        self.last_input = time.time()

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

            if t == "idle_animation":
                frames = sconf["frames"]
                f = random.choice(frames)
                if random.random() < sconf.get("happy_chance",0.2):
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
                for f in sconf["frames"]:
                    img = self.display.load(f)
                    self.display.show(img)
                    time.sleep(sconf.get("delay",2.0))
                self.state = "LOOK_AROUND"  # return to idle after cycle

            else:
                time.sleep(0.1)

# ---------------- main --------------------
if __name__ == "__main__":
    cfg = load_json(CONFIG_PATH, {})
    device = get_device()
    r = Rebecca(device, cfg)
    r.start()

    print("Rebecca running — type events (or Ctrl+C to exit):")
    try:
        while True:
            ev = input("> ").strip()
            if ev:
                r.event(ev)
    except KeyboardInterrupt:
        r.running = False
        print("Bye.")
