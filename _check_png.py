"""Check if PNG files are valid."""
import sys
import os
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))

from PIL import Image

# Check ayylmao.png
p = os.path.join(ROOT, "assets", "imgs", "ayylmao.png")
try:
    Image.open(p).verify()
    with Image.open(p) as img:
        print(f"ayylmao.png: OK ({img.size})")
except Exception as e:
    print(f"ayylmao.png: ERROR - {e}")

# Check sample preview pngs
previews = os.path.join(ROOT, "runtime", "previews")
if os.path.isdir(previews):
    for f in os.listdir(previews)[:5]:
        fp = os.path.join(previews, f)
        try:
            Image.open(fp).verify()
            with Image.open(fp) as img:
                print(f"{f}: OK ({img.size})")
        except Exception as e:
            print(f"{f}: ERROR - {e}")
