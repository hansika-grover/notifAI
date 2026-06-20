"""
Creatives: turn a matched story into a production-style ad creative + video script.

Two layers (text-to-image models can't render legible text):
  1. AI PHOTO  -- Cloudflare Workers AI (FLUX) makes a clean, IN-CONTEXT photo
                  with a person, grounded in the story. No text baked in.
  2. AD LAYER  -- Pillow composites the REAL grounded headline, a CTA pill, a
                  trend-graph accent and an eyebrow label BELOW the photo, so
                  text never crops or covers the image. Generic by design.
"""
import io
import os
import base64
import textwrap
import requests

from PIL import Image, ImageDraw, ImageFont

import config
import gemini_client

# Fallback subject per group (used only when Gemini isn't available).
SUBJECTS = {
    "insurance_finance":   "a relatable middle-aged American couple reviewing paperwork at a kitchen table in a bright modern home",
    "home_services":       "a friendly professional contractor in a clean uniform in front of a suburban house",
    "health_supplements":  "a healthy active adult smiling outdoors in soft natural morning light",
    "financial_publishing":"a focused adult reviewing financial charts on a laptop in a modern home office",
    "education_career":    "a confident adult learner with a laptop in a bright contemporary setting",
    "b2b":                 "a professional team collaborating in a modern bright office",
}
_DEFAULT_SUBJECT = "a relatable everyday American person in a bright modern setting"


def _font(bold=True, size=48):
    env = os.environ.get("AD_FONT_BOLD" if bold else "AD_FONT")
    candidates = [env] if env else []
    candidates += [
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
        ("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
    ]
    for p in candidates:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


def _image_prompt(article: dict, match: dict) -> tuple[str, str]:
    """A literal, in-context scene. Uses Gemini to ground the visual in the story."""
    title = (article.get("title") or "").strip()
    headline = (article.get("ad_headline") or "").strip()
    niche = match.get("niche_label", "")
    subject = SUBJECTS.get(match.get("niche"), _DEFAULT_SUBJECT)

    if gemini_client.available():
        ask = (
            "In ONE sentence, describe a literal, photographable advertising scene "
            f"for a '{niche}' ad reacting to this news. Show a real person and a "
            "setting directly relevant to the topic, subject in the upper-center, "
            "generous empty copy space along the bottom. No text, no logos. "
            "Just the visual.\n"
            f"NEWS HEADLINE: {title}\nAD ANGLE: {headline}"
        )
        scene = gemini_client.generate_text(ask)
        if scene:
            subject = scene.strip().rstrip(".")

    prompt = (
        f"Professional commercial advertising photograph. {subject}. "
        "Bright clean modern lighting, shallow depth of field, high-end DSLR look, "
        "authentic candid expression, subject framed in the upper-center, "
        "generous empty copy space across the bottom third, premium brand campaign "
        "aesthetic, photorealistic, sharp focus. "
        "Absolutely no text, no words, no letters, no logos, no watermark."
    )
    negative = ("text, words, letters, captions, logo, watermark, deformed hands, "
                "extra fingers, lowres, cartoon, cgi, oversaturated")
    return prompt, negative


def _cf_image(prompt: str) -> bytes | None:
    acc = os.environ.get("CF_ACCOUNT_ID", "")
    tok = os.environ.get("CF_API_TOKEN", "")
    if not acc or not tok:
        print("[creatives] cloudflare creds missing (CF_ACCOUNT_ID / CF_API_TOKEN)")
        return None
    url = (f"https://api.cloudflare.com/client/v4/accounts/{acc}"
           "/ai/run/@cf/black-forest-labs/flux-1-schnell")
    try:
        r = requests.post(url, headers={"Authorization": f"Bearer {tok}"},
                          json={"prompt": prompt}, timeout=90)
        if r.status_code != 200:
            print(f"[creatives] cloudflare HTTP {r.status_code}: {r.text[:160]}")
            return None
        return base64.b64decode(r.json()["result"]["image"])
    except Exception as e:
        print(f"[creatives] cloudflare error: {e}")
        return None


def _hex(s):
    s = s.lstrip("#")
    return tuple(int(s[i:i+2], 16) for i in (0, 2, 4))


def _cover(img, w, h):
    """Cover-fit, biased to the upper third so faces/subjects aren't cut off."""
    iw, ih = img.size
    scale = max(w / iw, h / ih)
    img = img.resize((int(iw * scale), int(ih * scale)), Image.LANCZOS)
    iw, ih = img.size
    left = (iw - w) // 2
    top = (ih - h) // 3
    return img.crop((left, top, left + w, top + h))


def _trend_graph(draw, x, y, w, h, color):
    vals = [0.15, 0.32, 0.26, 0.55, 0.7, 0.95]
    pts = [(x + int(w * i / (len(vals) - 1)), y + h - int(h * v))
           for i, v in enumerate(vals)]
    draw.line(pts, fill=color, width=5, joint="curve")
    for px, py in pts:
        draw.ellipse([px - 6, py - 6, px + 6, py + 6], fill=color)


def _compose_ad(base_bytes: bytes, headline: str, eyebrow: str,
                cta: str = "Learn More") -> bytes:
    """1080x1350 DR-style ad: photo on top, copy in a clean band beneath it."""
    W, H = 1080, 1350
    BG = (14, 17, 23)
    ACCENT = _hex(os.environ.get("AD_ACCENT", "#FF5D3B"))
    INK = (245, 247, 251)
    PHOTO_H = 838

    canvas = Image.new("RGB", (W, H), BG)
    try:
        photo = Image.open(io.BytesIO(base_bytes)).convert("RGB")
    except Exception:
        photo = Image.new("RGB", (W, PHOTO_H), (40, 44, 54))
    canvas.paste(_cover(photo, W, PHOTO_H), (0, 0))

    # soft gradient blend into the band (kept shallow so the subject stays clear)
    scrim = Image.new("L", (W, PHOTO_H), 0)
    sd = ImageDraw.Draw(scrim)
    band = 160
    for i in range(band):
        sd.line([(0, PHOTO_H - band + i), (W, PHOTO_H - band + i)],
                fill=int(255 * (i / band)))
    canvas.paste(Image.new("RGB", (W, PHOTO_H), BG), (0, 0), scrim)

    d = ImageDraw.Draw(canvas)
    d.rectangle([72, PHOTO_H - 4, 162, PHOTO_H], fill=ACCENT)          # accent rule
    d.text((72, PHOTO_H + 26), eyebrow.upper(), font=_font(True, 26), fill=ACCENT)

    wrapped = textwrap.fill(headline, width=24)
    d.multiline_text((72, PHOTO_H + 70), wrapped, font=_font(True, 58),
                     fill=INK, spacing=8)

    f_cta = _font(True, 30)
    tb = d.textbbox((0, 0), cta, font=f_cta)
    cw, ch = tb[2] - tb[0], tb[3] - tb[1]
    d.rounded_rectangle([72, H - 132, 72 + cw + 72, H - 132 + ch + 44],
                        radius=(ch + 44) // 2, fill=ACCENT)
    d.text((108, H - 110), cta, font=f_cta, fill=(12, 13, 17))
    _trend_graph(d, W - 250, H - 150, 170, 80, ACCENT)

    out = io.BytesIO()
    canvas.save(out, format="PNG")
    return out.getvalue()


_VIDEO_TMPL = """Scene Setup: 15s vertical smartphone video, warm natural daylight, authentic UGC feel, lived-in modern home.
Subject: a relatable adult, warm and sincere, talking to camera.
0:00-0:05: "Saw the news about {topic} and it got me thinking."
0:05-0:10: "{headline} -- worth understanding your options before anything changes."
0:10-0:15: "{desc} Tap below to learn more today." """


def _video_script(article, match, headline, desc) -> str:
    topic = (article.get("title") or "").strip()
    if gemini_client.available():
        prompt = (
            "Write a 15-second vertical UGC-style video ad script (Seedance format) "
            f"for a {match['niche_label']} advertiser tying into this news, in three "
            "beats (0:00-0:05, 0:05-0:10, 0:10-0:15) with a Scene Setup and Subject "
            "line. Base it only on the headline; invent no statistics or claims.\n"
            f"NEWS: {topic}\nAD HEADLINE: {headline}\nAD DESC: {desc}"
        )
        out = gemini_client.generate_text(prompt)
        if out:
            return out.strip()
    return _VIDEO_TMPL.format(topic=topic, headline=headline, desc=desc)


def make_creatives(article: dict, match: dict, allow_render: bool = True) -> dict:
    prompt, negative = _image_prompt(article, match)
    headline = article.get("ad_headline") or match.get("niche_label", "")
    desc = article.get("ad_description") or ""
    script = _video_script(article, match, headline, desc)

    image_path = None
    if allow_render and config.IMAGE_RENDER == "cloudflare":
        base = _cf_image(prompt)
        if base:
            ad_png = _compose_ad(base, headline, match.get("niche_label") or "Sponsored")
            os.makedirs(config.CREATIVES_DIR, exist_ok=True)
            fname = f"{article.get('id', 'creative')}.png"
            with open(os.path.join(config.CREATIVES_DIR, fname), "wb") as fh:
                fh.write(ad_png)
            image_path = f"/static/creatives/{fname}"

    return {"image_prompt": prompt, "image_negative": negative,
            "image_path": image_path, "video_script": script}