#!/usr/bin/env python3
import sys, socket, json
if len(sys.argv)<2:
    print("usage: rebecca_event.py <event>")
    exit()
sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
sock.sendto(json.dumps({"type":sys.argv[1]}).encode(), "/tmp/rebecca.sock")
sock.close()
