"""
Correlator: match a news story to the BEST ad niche, then write ad copy.

Two guards against hallucinated connections (your hard requirement):

  1. LEXICAL GATE (deterministic, no LLM): score the story against each niche's
     keyword set. Pick the best niche ONLY if its relevance clears
     NICHE_MATCH_THRESHOLD. Otherwise -> niche = None, no ad is written.

  2. LLM SELF-CHECK (only if a niche passed the gate): Gemini is told the exact
     keywords that matched and is instructed to set "relevant": false and write
     NOTHING if the link is a stretch. We pass the matched keywords as the only
     allowed basis for the connection, so it can't invent a relationship.

With no Gemini key, step 2 is replaced by a clean, honest template that only
uses facts already in the headline -- still no fabrication.
"""
import re

from config import NICHES, NICHE_MATCH_THRESHOLD
import gemini_client


def _word_present(kw: str, low: str) -> bool:
    """Whole-word / phrase match so 'rate' doesn't fire inside 'accelerate'."""
    return re.search(r"\b" + re.escape(kw) + r"\b", low) is not None


def _relevance(text: str, cfg: dict) -> tuple[float, list[str]]:
    """Grounded relevance: one specific (strong) phrase is enough; generic
    (weak) words need company. Returns (score 0..1, matched keywords)."""
    low = text.lower()
    strong = [kw for kw in cfg["strong"] if _word_present(kw, low)]
    weak = [kw for kw in cfg["weak"] if _word_present(kw, low)]
    score = min(1.0, len(strong) * 0.6 + len(weak) * 0.15)
    return score, strong + weak


def match_niche(article: dict) -> dict:
    """Return best niche + relevance + matched keywords (or niche=None)."""
    text = f"{article.get('title','')} {article.get('summary','')}"
    best_key, best_rel, best_kw = None, 0.0, []
    for key, cfg in NICHES.items():
        rel, matched = _relevance(text, cfg)
        if rel > best_rel:
            best_key, best_rel, best_kw = key, rel, matched

    if best_key is None or best_rel < NICHE_MATCH_THRESHOLD or not best_kw:
        return {"niche": None, "niche_label": None,
                "niche_relevance": round(best_rel, 3), "matched_keywords": best_kw}

    return {
        "niche": best_key,
        "niche_label": NICHES[best_key]["label"],
        "niche_relevance": round(best_rel, 3),
        "matched_keywords": best_kw,
    }


# --------------------------------------------------------------------------- #
#  Ad copy generation                                                         #
# --------------------------------------------------------------------------- #
_PROMPT = """You are a senior performance-marketing copywriter for US home-services and home-finance advertisers.

A news story has been matched to the ad niche "{label}" because it contains these terms: {kw}.

NEWS HEADLINE: {title}
NEWS SUMMARY: {summary}

Write ONE ad (headline + description) for a "{label}" advertiser that ties into this story.

STRICT RULES:
- Only proceed if the story genuinely relates to {label}. If the connection is a stretch or fabricated, set "relevant": false and leave headline/description empty.
- Base the angle ONLY on facts visible in the headline/summary. Do NOT invent statistics, events, quotes, or claims.
- No specific prices, rates, or guarantees unless they appear in the source text.
- Headline <= 60 characters. Description <= 150 characters.
- Make the headline sound like a real ad headline: specific, benefit-led, and action-oriented.
- Avoid generic news-explainer phrasing such as "what this means for you", "news update", "breaking", or "latest headlines".
- Description should connect the story's topic to a clear next step for the advertiser's service.
- Tone: catchy and useful, not fear-mongering or spammy.

Return ONLY this JSON:
{{"relevant": true/false, "reason": "one sentence on why it does/doesn't connect", "headline": "...", "description": "..."}}"""


def _template_ad(article: dict, match: dict) -> dict:
    """Honest fallback used when no Gemini key is set (or the call fails)."""
    niche = match.get("niche")
    label = match["niche_label"]
    kws = match["matched_keywords"]
    topic = kws[0] if kws else label.lower()
    templates = {
        "home_insurance": (
            "Check Your Home Coverage Today",
            "Storms, claims, or premium shifts in the news? Compare home insurance options built around your address.",
        ),
        "refinance": (
            "Could a Refi Lower Your Payment?",
            "When mortgage rates are in the headlines, see whether refinancing could fit your goals. Check options in minutes.",
        ),
        "home_loans": (
            "Find a Mortgage That Fits",
            "Housing news moves fast. Compare loan options and get a clearer path to your next home.",
        ),
        "roofing": (
            "Storm Damage? Book a Roof Check",
            "If roof or storm news hits your area, schedule an inspection and fix small issues before they spread.",
        ),
        "plumbing": (
            "Leaks Move Fast. So Should You.",
            "Pipe, drain, or water-heater trouble? Get a local plumber on the problem before damage grows.",
        ),
        "bathroom": (
            "Upgrade the Bathroom You Use Daily",
            "Home-improvement news has you planning? Explore shower, vanity, and full bath remodel options.",
        ),
    }
    headline, desc = templates.get(
        niche,
        (
            f"{label} Options Worth Checking",
            f"With {topic} in the news, compare {label.lower()} options and take the next step with confidence.",
        ),
    )
    return {
        "ad_relevant": 1,
        "ad_headline": headline[:60],
        "ad_description": desc[:150],
        "ad_reason": f"Template fallback; matched on: {', '.join(kws) or topic}.",
    }


def make_ad(article: dict, match: dict) -> dict:
    """Generate ad copy for a story whose niche already passed the lexical gate."""
    if not match.get("niche"):
        return {"ad_relevant": 0, "ad_headline": None, "ad_description": None,
                "ad_reason": "No niche cleared the relevance threshold; no ad generated."}

    if gemini_client.available():
        prompt = _PROMPT.format(
            label=match["niche_label"],
            kw=", ".join(match["matched_keywords"]) or "(none)",
            title=article.get("title", ""),
            summary=(article.get("summary", "") or "")[:400],
        )
        result = gemini_client.generate_json(prompt)
        if result is not None:
            if not result.get("relevant"):
                return {"ad_relevant": 0, "ad_headline": None, "ad_description": None,
                        "ad_reason": result.get("reason", "LLM judged the link not genuine.")}
            return {
                "ad_relevant": 1,
                "ad_headline": (result.get("headline") or "").strip()[:80],
                "ad_description": (result.get("description") or "").strip()[:200],
                "ad_reason": result.get("reason", "")[:300],
            }
        # Gemini failed -> fall through to template

    return _template_ad(article, match)


def correlate(article: dict) -> dict:
    """Full step: match niche + (maybe) write ad. Mutates and returns article."""
    match = match_niche(article)
    article.update({
        "niche": match["niche"],
        "niche_label": match["niche_label"],
        "niche_relevance": match["niche_relevance"],
    })
    article.update(make_ad(article, match))
    return article
