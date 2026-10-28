from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageChops
import math

S = 2                      # 2 倍超取樣，最後縮小讓線條更平滑
W, H = 2500 * S, 1686 * S
COLS = [0, 833, 1667, 2500]
ROWS = [0, 843, 1686]

BLACK = "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc"
MEDIUM = "/usr/share/fonts/opentype/noto/NotoSansCJK-Medium.ttc"
TC = 3
f_title = ImageFont.truetype(BLACK, 96 * S, index=TC)
f_sub = ImageFont.truetype(MEDIUM, 50 * S, index=TC)
f_q = ImageFont.truetype(BLACK, 190 * S, index=TC)
f_ai = ImageFont.truetype(BLACK, 70 * S, index=TC)

TILES = [
    ("最近收藏", "看看剛存的文章", ("#A78BFA", "#6D28D9"), "clock"),
    ("分類總覽", "各類收藏一覽", ("#60A5FA", "#2563EB"), "folder"),
    ("搜尋收藏", "用關鍵字快速找", ("#34D399", "#0F9D7A"), "search"),
    ("美食口袋", "餐廳美食清單", ("#FDBA74", "#EA580C"), "food"),
    ("AI 工具", "AI／程式開發", ("#F472B6", "#BE185D"), "robot"),
    ("使用說明", "指令與小技巧", ("#FCD34D", "#D97706"), "help"),
]


def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def vgradient(size, top, bottom):
    w, h = size
    g = Image.new("RGB", (1, h))
    t, b = hex2rgb(top), hex2rgb(bottom)
    for y in range(h):
        k = y / max(h - 1, 1)
        g.putpixel((0, y), tuple(int(t[i] + (b[i] - t[i]) * k) for i in range(3)))
    return g.resize((w, h))


def dgradient(size, c1, c2):
    """對角漸層（左上亮、右下深）"""
    w, h = size
    a, b = hex2rgb(c1), hex2rgb(c2)
    base = Image.linear_gradient("L").resize((w, h)).rotate(-45, expand=False)
    grad = Image.new("L", (w, h))
    for x in range(0, w, 4):
        pass
    # 用兩個線性漸層相加得到對角效果
    gx = Image.linear_gradient("L").rotate(90).resize((w, h))
    gy = Image.linear_gradient("L").resize((w, h))
    mask = ImageChops.add(gx.point(lambda v: v // 2), gy.point(lambda v: v // 2))
    return Image.composite(Image.new("RGB", (w, h), b), Image.new("RGB", (w, h), a), mask)


# ── 背景 ───────────────────────────────────────────
img = vgradient((W, H), "#FBF7F1", "#F1E9DD").convert("RGBA")

# 背景淡淡的圓點紋理
dots = Image.new("RGBA", (W, H), (0, 0, 0, 0))
dd = ImageDraw.Draw(dots)
for yy in range(0, H, 60 * S):
    for xx in range((yy // (60 * S)) % 2 * 30 * S, W, 60 * S):
        dd.ellipse([xx, yy, xx + 5 * S, yy + 5 * S], fill=(190, 170, 140, 40))
img = Image.alpha_composite(img, dots)

PAD = 26 * S
RADIUS = 64 * S


def stroke_icon(kind, box, color=(255, 255, 255, 255)):
    """在 box (x0,y0,x1,y1) 內畫白色線條圖示，回傳 RGBA 圖層"""
    x0, y0, x1, y1 = box
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    r = (x1 - x0) / 2
    lw = int(r * 0.13)

    def line(pts, w=lw):
        d.line(pts, fill=color, width=w, joint="curve")
        for p in (pts[0], pts[-1]):
            d.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2], fill=color)

    if kind == "clock":
        rr = r * 0.82
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=color, width=lw)
        line([(cx, cy), (cx, cy - rr * 0.55)])
        line([(cx, cy), (cx + rr * 0.42, cy + rr * 0.22)])
        d.ellipse([cx - lw * 0.8, cy - lw * 0.8, cx + lw * 0.8, cy + lw * 0.8], fill=color)
    elif kind == "folder":
        w2, h2 = r * 0.95, r * 0.68
        top = cy - h2 + r * 0.08
        d.rounded_rectangle([cx - w2, top + r * 0.2, cx + w2, cy + h2], radius=int(r * 0.16),
                            outline=color, width=lw)
        tab = [(cx - w2 + lw / 2, top + r * 0.2), (cx - w2 + lw / 2, top),
               (cx - r * 0.2, top), (cx - r * 0.02, top + r * 0.2)]
        line(tab)
        line([(cx - w2 + r * 0.05, cy - r * 0.05), (cx + w2 - r * 0.05, cy - r * 0.05)])
    elif kind == "search":
        rr = r * 0.52
        ox, oy = cx - r * 0.18, cy - r * 0.18
        d.ellipse([ox - rr, oy - rr, ox + rr, oy + rr], outline=color, width=lw)
        a = math.radians(45)
        line([(ox + rr * math.cos(a) + lw * 0.3, oy + rr * math.sin(a) + lw * 0.3),
              (cx + r * 0.72, cy + r * 0.72)], w=int(lw * 1.25))
        # 鏡面高光
        d.arc([ox - rr * 0.62, oy - rr * 0.62, ox + rr * 0.62, oy + rr * 0.62], 200, 260,
              fill=color, width=int(lw * 0.6))
    elif kind == "food":
        # 碗
        bw = r * 0.92
        by = cy + r * 0.02
        d.chord([cx - bw, by - bw * 0.95, cx + bw, by + bw * 0.95], 0, 180, outline=color, width=lw)
        line([(cx - bw - lw * 0.2, by), (cx + bw + lw * 0.2, by)])
        line([(cx - r * 0.32, by + bw * 0.95 + lw * 0.1), (cx + r * 0.32, by + bw * 0.95 + lw * 0.1)])
        # 筷子
        line([(cx + r * 0.15, by - r * 0.08), (cx + r * 0.85, by - r * 0.92)], w=int(lw * 0.8))
        line([(cx + r * 0.38, by - r * 0.04), (cx + r * 0.98, by - r * 0.68)], w=int(lw * 0.8))
        # 蒸氣
        for sx in (-0.45, -0.12):
            pts = []
            for t in range(0, 41):
                yy = by - r * 0.25 - t / 40 * r * 0.62
                xx = cx + sx * r + math.sin(t / 40 * math.pi * 2) * r * 0.07
                pts.append((xx, yy))
            line(pts, w=int(lw * 0.75))
    elif kind == "robot":
        hw, hh = r * 0.78, r * 0.6
        top = cy - hh + r * 0.15
        d.rounded_rectangle([cx - hw, top, cx + hw, cy + hh + r * 0.15], radius=int(r * 0.28),
                            outline=color, width=lw)
        line([(cx, top), (cx, top - r * 0.28)])
        d.ellipse([cx - lw * 1.3, top - r * 0.28 - lw * 1.3, cx + lw * 1.3, top - r * 0.28 + lw * 1.3],
                  fill=color)
        ey = cy + r * 0.1
        for ex in (-0.33, 0.33):
            d.ellipse([cx + ex * r - lw * 1.15, ey - lw * 1.15, cx + ex * r + lw * 1.15, ey + lw * 1.15],
                      fill=color)
        d.arc([cx - r * 0.28, ey + r * 0.02, cx + r * 0.28, ey + r * 0.42], 20, 160, fill=color,
              width=int(lw * 0.8))
        for side in (-1, 1):
            line([(cx + side * hw, cy + r * 0.12), (cx + side * (hw + r * 0.18), cy + r * 0.12)])
    elif kind == "help":
        bw, bh = r * 0.9, r * 0.72
        d.rounded_rectangle([cx - bw, cy - bh - r * 0.05, cx + bw, cy + bh - r * 0.15],
                            radius=int(r * 0.32), outline=color, width=lw)
        # 對話框尾巴
        tail = [(cx - r * 0.35, cy + bh - r * 0.15 - lw / 2), (cx - r * 0.5, cy + bh + r * 0.2),
                (cx - r * 0.05, cy + bh - r * 0.15 - lw / 2)]
        d.polygon(tail, fill=color)
        d.text((cx, cy - r * 0.12), "?", font=ImageFont.truetype(BLACK, int(r * 1.05), index=TC),
               fill=color, anchor="mm")
    return layer


def shadow_layer(box, radius, offset, blur, alpha):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle(
        [box[0] + offset[0], box[1] + offset[1], box[2] + offset[0], box[3] + offset[1]],
        radius=radius, fill=(90, 60, 30, alpha))
    return layer.filter(ImageFilter.GaussianBlur(blur))


for i, (title, sub, (c1, c2), icon) in enumerate(TILES):
    col, row = i % 3, i // 3
    x0, x1 = COLS[col] * S, COLS[col + 1] * S
    y0, y1 = ROWS[row] * S, ROWS[row + 1] * S
    card = (x0 + PAD, y0 + PAD, x1 - PAD, y1 - PAD)

    # 卡片陰影 + 白卡
    img = Image.alpha_composite(img, shadow_layer(card, RADIUS, (0, 14 * S), 26 * S, 55))
    cl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    cd = ImageDraw.Draw(cl)
    cd.rounded_rectangle(card, radius=RADIUS, fill=(255, 255, 255, 255))
    # 卡片頂端淡淡的主題色
    tint = vgradient((card[2] - card[0], int((card[3] - card[1]) * 0.55)), c1, "#FFFFFF").convert("RGBA")
    tint.putalpha(46)
    tmask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(tmask).rounded_rectangle(card, radius=RADIUS, fill=255)
    tl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    tl.paste(tint, (card[0], card[1]))
    tl.putalpha(ImageChops.multiply(tl.getchannel("A"), tmask))
    img = Image.alpha_composite(img, cl)
    img = Image.alpha_composite(img, tl)
    ImageDraw.Draw(img).rounded_rectangle(card, radius=RADIUS, outline=(235, 225, 210, 255), width=2 * S)

    # 圖示圓
    ccx = (card[0] + card[2]) // 2
    ccy = card[1] + int(250 * S)
    R = int(150 * S)
    cbox = (ccx - R, ccy - R, ccx + R, ccy + R)
    img = Image.alpha_composite(img, shadow_layer(cbox, R, (0, 16 * S), 22 * S, 70))
    grad = dgradient((2 * R, 2 * R), c1, c2).convert("RGBA")
    m = Image.new("L", (2 * R, 2 * R), 0)
    ImageDraw.Draw(m).ellipse([0, 0, 2 * R - 1, 2 * R - 1], fill=255)
    grad.putalpha(m)
    gl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gl.paste(grad, (cbox[0], cbox[1]))
    img = Image.alpha_composite(img, gl)
    # 圓上方高光
    hl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(hl).ellipse([ccx - R * 0.72, ccy - R * 0.92, ccx + R * 0.72, ccy - R * 0.08],
                               fill=(255, 255, 255, 50))
    img = Image.alpha_composite(img, hl.filter(ImageFilter.GaussianBlur(10 * S)))

    ir = int(R * 0.56)
    img = Image.alpha_composite(img, stroke_icon(icon, (ccx - ir, ccy - ir, ccx + ir, ccy + ir)))

    # 文字
    d = ImageDraw.Draw(img)
    ty = card[1] + int(530 * S)
    d.text((ccx, ty), title, font=f_title, fill=(43, 37, 33, 255), anchor="mm")
    d.text((ccx, ty + int(100 * S)), sub, font=f_sub, fill=(140, 128, 115, 255), anchor="mm")
    # 主題色小底線
    lw2 = int(70 * S)
    d.rounded_rectangle([ccx - lw2 // 2, ty + int(160 * S), ccx + lw2 // 2, ty + int(170 * S)],
                        radius=5 * S, fill=hex2rgb(c2) + (200,))

out = img.convert("RGB").resize((2500, 1686), Image.LANCZOS)
out.save("/mnt/user-data/outputs/richmenu.png", optimize=True)
import os
print(os.path.getsize("/mnt/user-data/outputs/richmenu.png"))
