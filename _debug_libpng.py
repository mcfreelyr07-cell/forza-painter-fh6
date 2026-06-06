"""Test all possible sources of libpng errors."""
import sys
import os
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))

# Test 1: cv2.imread with various files
print("=== Test 1: cv2.imread ===")
import cv2
previews_dir = os.path.join(ROOT, "runtime", "previews")
if os.path.isdir(previews_dir):
    files = [f for f in os.listdir(previews_dir) if f.endswith(".png")]
    for f in files[:20]:
        path = os.path.join(previews_dir, f)
        img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
        if img is None:
            print(f"FAILED: {f}")
        # else: print(f"OK: {f}")

# Test 2: Check for bad PNG signatures
print("=== Test 2: PNG signature check ===")
for root_dir, dirs, files in os.walk(ROOT):
    for f in files:
        if f.endswith(".png"):
            path = os.path.join(root_dir, f)
            with open(path, "rb") as fp:
                sig = fp.read(8)
                if sig[:4] != b"\x89PNG":
                    print(f"BAD SIG: {path}")

print("=== Done ===")
