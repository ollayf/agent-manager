#!/usr/bin/env python3
"""Turn a still (any aspect) into a 16:9 push-in clip that fills the frame.

    photo.py IMG.jpg OUT.mp4 [--seconds 5] [--zoom 0.09]

The photo sits full-height in the middle; a blurred, darkened copy of itself fills the sides
(no black bars, nothing cropped off the subject). Slow push-in, 1920x1080, 30 fps, no audio.
Insert it with insert_clips (includeAudio n/a) and give it a place label like any other scene.
"""
import argparse, subprocess, pathlib
from PIL import Image, ImageFilter
ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("img"); ap.add_argument("out"); ap.add_argument("--seconds", type=float, default=5)
ap.add_argument("--zoom", type=float, default=0.09, help="total zoom over the clip (0.09 = 9%%)")
a = ap.parse_args()
im = Image.open(a.img).convert("RGB"); W, H = 3840, 2160
sh = int(W * im.height / im.width)
bg = im.resize((W, sh)).crop((0, max(0, (sh - H) // 2), W, max(0, (sh - H) // 2) + H)).resize((W, H))
bg = Image.eval(bg.filter(ImageFilter.GaussianBlur(60)), lambda v: int(v * .55))
fg = im.resize((int(H * im.width / im.height), H), Image.LANCZOS)
if fg.width > W: fg = im.resize((W, int(W * im.height / im.width)), Image.LANCZOS)
bg.paste(fg, ((W - fg.width) // 2, (H - fg.height) // 2))
still = pathlib.Path(a.out).with_suffix(".16x9.jpg"); bg.save(still, quality=93)
n = int(a.seconds * 30); step = a.zoom / n
subprocess.run(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", str(still), "-vf",
                f"scale=3840:2160,zoompan=z='1+{step:.6f}*on':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={n}:s=1920x1080:fps=30,format=yuv420p",
                "-frames:v", str(n), "-c:v", "libx264", "-crf", "14", "-preset", "slow", a.out], check=True)
print(a.out)
