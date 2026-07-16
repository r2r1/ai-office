"""
Генерирует OG/Twitter-card превью для лендинга (webapp/public/og-image.png) и
favicon (webapp/public/favicon.png) — до этого в проекте не было НИ ОДНОГО
графического ассета: /webapp/index.html не отдавал ни og:image, ни favicon,
ни meta description. Любая ссылка на продукт, отправленная в Telegram/VK/
почту/мессенджер, показывала голый заголовок без превью — реальный SMM-разрыв,
который эта правка закрывает.

Палитра и композиция — ДОСЛОВНО из существующего бренда (LandingView.tsx):
тёмный фон, Mercury-градиент (#a0e0ab → #ffac2e → #a52d25), тот же заголовок,
что и в hero. Не новый арт-директ, а перенос уже утверждённого стиля в
формат превью-карточки.

Запуск: python scripts/gen_og_image.py
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter

OUT_DIR = "webapp/public"
FONT_DIR = "C:/Windows/Fonts"

BG = (10, 9, 8)
MERCURY_STOPS = [(0.0, (160, 224, 171)), (0.5, (255, 172, 46)), (1.0, (165, 45, 37))]


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def mercury_color(t: float) -> tuple:
    t = max(0.0, min(1.0, t))
    for i in range(len(MERCURY_STOPS) - 1):
        t0, c0 = MERCURY_STOPS[i]
        t1, c1 = MERCURY_STOPS[i + 1]
        if t0 <= t <= t1:
            local = (t - t0) / (t1 - t0) if t1 > t0 else 0
            return lerp(c0, c1, local)
    return MERCURY_STOPS[-1][1]


def draw_gradient_text(base: Image.Image, xy, text, font, stops_offset=0.0):
    """Рисует текст с горизонтальным Mercury-градиентом (как background-clip:
    text в CSS) — рендерим текст маской, заливаем градиентом через неё."""
    x, y = xy
    mask = Image.new("L", base.size, 0)
    ImageDraw.Draw(mask).text((x, y), text, font=font, fill=255)
    bbox = font.getbbox(text)
    w = bbox[2] - bbox[0]
    grad = Image.new("RGB", base.size, BG)
    gd = ImageDraw.Draw(grad)
    for px in range(x, x + w + 1):
        t = (px - x) / max(1, w) + stops_offset
        gd.line([(px, y - 5), (px, y + font.size + 20)], fill=mercury_color(t))
    base.paste(grad, (0, 0), mask)


def make_og_image():
    W, H = 1200, 630
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # Амбиентное свечение (тот же приём, что радиальные пятна на лендинге)
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([-200, -250, 500, 350], fill=(20, 45, 28))
    gd.ellipse([850, 250, 1500, 800], fill=(50, 22, 10))
    glow = glow.filter(ImageFilter.GaussianBlur(140))
    img = Image.blend(img, Image.blend(img, glow, 0.55), 1.0)
    draw = ImageDraw.Draw(img)

    f_badge = ImageFont.truetype(f"{FONT_DIR}/arial.ttf", 22)
    f_h1 = ImageFont.truetype(f"{FONT_DIR}/arial.ttf", 64)
    f_h1_italic = ImageFont.truetype(f"{FONT_DIR}/ariali.ttf", 64)
    f_sub = ImageFont.truetype(f"{FONT_DIR}/arial.ttf", 27)
    f_word = ImageFont.truetype(f"{FONT_DIR}/arial.ttf", 26)

    mx = 90

    # Wordmark "AI office" + акцентная точка (как в Nav лендинга)
    draw.ellipse([mx, 68, mx + 14, 82], fill=mercury_color(0.5))
    draw.text((mx + 26, 56), "AI", font=f_word, fill=(240, 240, 240))
    w_ai = draw.textlength("AI ", font=f_word)
    draw.text((mx + 26 + w_ai, 56), "office", font=ImageFont.truetype(f"{FONT_DIR}/ariali.ttf", 26), fill=(150, 150, 150))

    # Бейдж "Business Operating System"
    badge_y = 140
    draw.rounded_rectangle([mx, badge_y, mx + 330, badge_y + 40], radius=20, outline=(70, 70, 70), width=1)
    draw.ellipse([mx + 18, badge_y + 17, mx + 24, badge_y + 23], fill=(160, 224, 171))
    draw.text((mx + 34, badge_y + 9), "Business Operating System", font=f_badge, fill=(200, 200, 200))

    # Заголовок — две строки, вторая с Mercury-градиентом (как hero на лендинге)
    draw.text((mx, 210), "Поставьте цель.", font=f_h1, fill=(245, 245, 245))
    draw_gradient_text(img, (mx, 290), "Офис сам её достигнет.", f_h1_italic)
    draw = ImageDraw.Draw(img)  # draw_gradient_text перерисовало img — новый Draw

    # Подзаголовок
    sub = "Живая операционная система компании: сама изучает рынок,"
    sub2 = "решает, что делать дальше, и берёт бизнес на себя."
    draw.text((mx, 400), sub, font=f_sub, fill=(160, 160, 160))
    draw.text((mx, 436), sub2, font=f_sub, fill=(160, 160, 160))

    img.save(f"{OUT_DIR}/og-image.png", "PNG", optimize=True)
    print(f"OK: {OUT_DIR}/og-image.png ({W}x{H})")


def make_favicon():
    """Простая квадратная иконка: тёмный фон + Mercury-точка, тот же знак,
    что и в Nav (см. LandingView.tsx: <span> с background: MERCURY)."""
    size = 256
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, size, size], radius=56, fill=(10, 9, 8, 255))
    cx, cy, r = size // 2, size // 2, 62
    # Радиальный Mercury-градиент внутри круга
    dot = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    dd = ImageDraw.Draw(dot)
    steps = 60
    for i in range(steps, 0, -1):
        t = i / steps
        rad = int(r * t)
        dd.ellipse([cx - rad, cy - rad, cx + rad, cy + rad], fill=(*mercury_color(1 - t), 255))
    img = Image.alpha_composite(img, dot)
    img.save(f"{OUT_DIR}/favicon.png", "PNG")
    # Многоразмерный .ico для широкой browser-совместимости
    img.save(f"{OUT_DIR}/favicon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128)])
    print(f"OK: {OUT_DIR}/favicon.png + favicon.ico")


if __name__ == "__main__":
    import os
    os.makedirs(OUT_DIR, exist_ok=True)
    make_og_image()
    make_favicon()
