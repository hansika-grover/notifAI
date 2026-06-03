"""
Central configuration for the Viral News -> Ad pipeline.

Everything tunable lives here so you don't have to dig through the code.
Secrets (the Gemini key) come from a .env file or your environment.
"""
import os
from pathlib import Path

# --- Load .env if present (no hard dependency on python-dotenv) -------------
def _load_env():
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

_load_env()

# --- Paths ------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
DB_PATH = os.environ.get("DB_PATH", str(BASE_DIR / "news.db"))

# --- Market / refresh -------------------------------------------------------
COUNTRY = "US"
LANG = "en-US"
CEID = "US:en"

# How often the pipeline re-fetches. Kept at 2h so the feed stays relevant
# without filling up with noise. Minimum sensible value ~1h.
REFRESH_HOURS = float(os.environ.get("REFRESH_HOURS", "2"))

# How many "top" stories to surface in the dashboard.
TOP_N = int(os.environ.get("TOP_N", "5"))

# "niche"  -> only fetch stories about the ad niches (recommended: keeps the
#             news <-> ad correlation honest, nothing to hallucinate).
# "general"-> fetch general top headlines too (most won't match a niche).
NEWS_SCOPE = os.environ.get("NEWS_SCOPE", "niche")

# Max articles pulled per niche query per refresh (keeps memory tiny).
MAX_PER_QUERY = int(os.environ.get("MAX_PER_QUERY", "12"))

# --- Gemini (free tier) -----------------------------------------------------
# Get a free key at https://aistudio.google.com/apikey  (no credit card).
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
# 2.5-flash-lite has the most generous free quota (~15 rpm / 1000 rpd) and is
# the lightest. Swap to gemini-2.5-flash for higher quality copy.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)

# --- Ad niches --------------------------------------------------------------
# Each niche has a Google-News query plus two keyword tiers used to GROUND the
# news<->niche match (no fuzzy guessing, no hallucination):
#   strong = specific, unambiguous signals. One match is enough to connect.
#   weak   = supporting/contextual words. Risky alone, so they need company.
# Relevance = min(1.0, strong_hits*0.6 + weak_hits*0.15).
NICHES = {
    "home_insurance": {
        "label": "Home Insurance",
        "query": "homeowners insurance OR home insurance OR property insurance",
        "strong": [
            "home insurance", "homeowners insurance", "homeowner insurance",
            "property insurance", "flood insurance", "insurance premium",
            "insurance claim", "insurance rate", "home insurer", "policyholder",
        ],
        "weak": ["insurance", "insurer", "premium", "deductible", "coverage",
                 "storm damage", "hurricane", "wildfire"],
    },
    "refinance": {
        "label": "Mortgage Refinance",
        "query": "mortgage refinance OR refinancing OR mortgage rates",
        "strong": ["refinance", "refinancing", "refi", "cash-out refinance",
                   "mortgage rate", "mortgage interest rate"],
        "weak": ["interest rate", "rate cut", "lower rate", "monthly payment",
                 "federal reserve", "fed meeting", "fed rate"],
    },
    "home_loans": {
        "label": "Home Loans / Mortgages",
        "query": "mortgage OR home loan OR housing market",
        "strong": ["mortgage", "home loan", "homebuyer", "first-time buyer",
                   "down payment", "fha loan", "housing market", "home prices"],
        "weak": ["housing", "lending", "loan", "home buying", "affordability",
                 "real estate"],
    },
    "roofing": {
        "label": "Roofing Services",
        "query": "roof repair OR roofing OR roof storm damage",
        "strong": ["roof", "roofing", "shingles", "roof repair",
                   "roof replacement", "roofer", "leaking roof"],
        "weak": ["hail damage", "storm damage", "hail", "attic"],
    },
    "plumbing": {
        "label": "Plumbing Services",
        "query": "plumbing OR burst pipe OR water heater",
        "strong": ["plumbing", "plumber", "burst pipe", "water heater",
                   "sewer line", "frozen pipes", "water leak"],
        "weak": ["pipe", "sewer", "drain", "leak", "flooding"],
    },
    "bathroom": {
        "label": "Bathroom Remodeling",
        "query": "bathroom remodel OR bathroom renovation OR home renovation",
        "strong": ["bathroom remodel", "bathroom renovation", "bath remodel",
                   "shower remodel", "home renovation", "home improvement"],
        "weak": ["bathroom", "shower", "bathtub", "vanity", "remodeling",
                 "renovation"],
    },
}

# A niche is assigned only if its grounded relevance clears this bar. Below it,
# the story is "no strong match" and NO ad copy is invented. With the formula
# above: one strong keyword (0.6) clears it; one weak keyword alone (0.15) does
# not. This is the main guard against fabricated connections.
NICHE_MATCH_THRESHOLD = float(os.environ.get("NICHE_MATCH_THRESHOLD", "0.3"))
