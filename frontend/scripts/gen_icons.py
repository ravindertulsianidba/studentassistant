"""Generate platform-ready icon derivatives from the approved GotU icon.

Produces (in assets/images/):
- icon.png            1024x1024 full-bleed dark green + feather (no white canvas/corners)
- adaptive-icon.png   1024x1024 transparent foreground (feather+accents) in adaptive safe zone
- notification-icon.png 256x256 monochrome white glyph, transparent bg
- favicon.png         48x48 (primary downscaled)
- splash-image.png    1024x1024 transparent feather for splash
Prints the dominant dark-green hex for adaptiveIcon backgroundColor.
"""
import os
from PIL import Image, ImageDraw

SRC = os.environ.get("SRC", "/tmp/approved_icon.png")
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "images")
BG = (46, 63, 50)          # dominant dark green sampled from the approved icon (~#2E3F32)
BG_HEX = "#2E3F32"

im = Image.open(SRC).convert("RGB")
W, H = im.size
px = im.load()

# Detect the GREEN tile interior (excludes the white border ring, drop shadow and canvas).
gxs, gys = [], []
for y in range(0, H, 2):
    for x in range(0, W, 2):
        r, g, b = px[x, y]
        if g > r + 4 and g > b + 4 and (r + g + b) < 170:
            gxs.append(x); gys.append(y)
gb = (min(gxs) + 8, min(gys) + 8, max(gxs) - 8, max(gys) - 8)

# Interior mask = green tile bbox only (feather + accents live inside; border excluded).
interior = Image.new("L", (W, H), 0)
ImageDraw.Draw(interior).rounded_rectangle(gb, radius=72, fill=255)
imask = interior.load()

# Artwork alpha from colour distance to the dark-green background, clipped to the interior.
art = Image.new("L", (W, H), 0)
ap = art.load()
for y in range(H):
    for x in range(W):
        if imask[x, y] == 0:
            continue
        r, g, b = px[x, y]
        dist = ((r - BG[0]) ** 2 + (g - BG[1]) ** 2 + (b - BG[2]) ** 2) ** 0.5
        a = int(max(0, min(255, (dist - 70) * 1.7)))
        ap[x, y] = a

# Tight crop to the tile interior so scaling keeps the feather centred with breathing room.
sq_box = gb
art_c = art.crop(sq_box)
src_c = im.crop(sq_box)

def paste_art(canvas, size, art_layer, rgb_layer=None, color=None):
    a = art_layer.resize((size, size), Image.LANCZOS)
    off = (canvas.size[0] - size) // 2
    if color:  # solid-colour glyph (notification)
        glyph = Image.new("RGBA", (size, size), color + (0,))
        glyph.putalpha(a)
        canvas.paste(glyph, (off, off), glyph)
    else:      # real artwork colours
        rgb = rgb_layer.resize((size, size), Image.LANCZOS).convert("RGBA")
        rgb.putalpha(a)
        canvas.paste(rgb, (off, off), rgb)
    return canvas

os.makedirs(OUT, exist_ok=True)

# 1) Primary icon: full-bleed green + feather at ~86% (breathing room).
icon = Image.new("RGBA", (1024, 1024), BG + (255,))
paste_art(icon, 880, art_c, rgb_layer=src_c)
icon.convert("RGB").save(os.path.join(OUT, "icon.png"))

# 2) Adaptive foreground: transparent, artwork within 66% safe zone.
adaptive = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
paste_art(adaptive, 680, art_c, rgb_layer=src_c)
adaptive.save(os.path.join(OUT, "adaptive-icon.png"))

# 3) Notification icon: monochrome white glyph, transparent.
notif = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
paste_art(notif, 200, art_c, color=(255, 255, 255))
notif.save(os.path.join(OUT, "notification-icon.png"))

# 4) Favicon.
icon.convert("RGB").resize((48, 48), Image.LANCZOS).save(os.path.join(OUT, "favicon.png"))

# 5) Splash feather (transparent).
splash = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
paste_art(splash, 520, art_c, rgb_layer=src_c)
splash.save(os.path.join(OUT, "splash-image.png"))

print(f"generated derivatives in {OUT}; adaptive backgroundColor={BG_HEX}")
