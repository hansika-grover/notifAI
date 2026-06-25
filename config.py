"""
Central configuration for the NotifAI pipeline.

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
            val = val.strip()
            if val and val[0] in "\"'":
                q = val[0]
                end = val.find(q, 1)
                val = val[1:end] if end != -1 else val[1:]
            elif "#" in val:
                val = val.split("#", 1)[0].strip()
            os.environ.setdefault(key.strip(), val)

_load_env()

# --- Paths ------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
DB_PATH = os.environ.get("DB_PATH", str(BASE_DIR / "news.db"))

# --- Market / refresh -------------------------------------------------------
COUNTRY = "US"
LANG = "en-US"
CEID = "US:en"

REFRESH_HOURS = float(os.environ.get("REFRESH_HOURS", "2"))
TOP_N = int(os.environ.get("TOP_N", "5"))                 # global "All" top
TOP_PER_NICHE = int(os.environ.get("TOP_PER_NICHE", "5")) # per-niche top
NEWS_SCOPE = os.environ.get("NEWS_SCOPE", "niche")
MAX_PER_QUERY = int(os.environ.get("MAX_PER_QUERY", "12"))

# With many niches, each one fires its own Google News query. That can be slow
# and can get your IP throttled. This caps how many niche queries actually run
# per sync (0 = no cap / fetch all). Matching still runs against ALL niches;
# this only limits FETCHING. Niches are fetched in the order they appear below,
# so put your priorities first.
MAX_NICHE_QUERIES = int(os.environ.get("MAX_NICHE_QUERIES", "0"))

# --- Gemini (free tier) -----------------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite")
GEMINI_ENDPOINT = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)
# --- Creatives / image rendering --------------------------------------------
IMAGE_RENDER = os.environ.get("IMAGE_RENDER", "none")          # none | cloudflare
MAX_IMAGES_PER_SYNC = int(os.environ.get("MAX_IMAGES_PER_SYNC", "5"))
CREATIVES_DIR = os.environ.get("CREATIVES_DIR", str(BASE_DIR / "static" / "creatives"))
AD_ACCENT = os.environ.get("AD_ACCENT", "#FF5D3B")             # headline/CTA accent


# --- Ad niches --------------------------------------------------------------
# Each niche: a Google-News query + two keyword tiers used to GROUND the
# news<->niche match (no fuzzy guessing).
#   strong = specific, unambiguous signals. One match is enough to connect.
#   weak   = supporting/contextual words. Need company to count.
# Relevance = min(1.0, strong_hits*0.6 + weak_hits*0.15).
NICHES = {
    "insurance_finance": {
        "label": "Insurance, Finance & Legal",
        "query": "mortgage rates OR home insurance OR auto insurance OR Medicare OR personal loan OR debt relief OR credit score OR personal injury lawsuit",
        "strong": [
            "auto insurance", "car insurance", "vehicle insurance",
            "home insurance", "homeowners insurance", "property insurance",
            "flood insurance", "insurance premium", "insurance claim",
            "life insurance", "term life", "whole life",
            "health insurance", "health plan", "obamacare", "affordable care act",
            "medicare advantage", "medicare part c", "medicare", "medigap",
            "medicare supplement", "refinance", "refinancing", "refi",
            "cash-out refinance", "mortgage rate", "reverse mortgage", "hecm",
            "mortgage", "home loan", "homebuyer", "first-time buyer", "fha loan",
            "housing market", "home prices", "debt consolidation", "debt relief",
            "debt settlement", "personal loan", "installment loan",
            "credit repair", "credit score", "credit report", "bad credit",
            "tax relief", "tax debt", "irs debt", "back taxes",
            "business funding", "merchant cash advance", "business loan", "sba loan",
            "personal injury", "accident lawyer", "injury lawsuit", "mass tort",
            "class action", "workers compensation", "workers comp",
            "social security disability", "ssdi",
        ],
        "weak": ["insurance", "insurer", "premium", "deductible", "coverage",
                 "policy", "seniors", "loan", "lending", "credit", "debt",
                 "interest rate", "fed rate", "home equity", "retirement", "irs",
                 "taxes", "capital", "financing", "lawsuit", "settlement",
                 "attorney", "accident", "disability", "benefits"],
    },
    "home_services": {
        "label": "Home Services",
        "query": "roofing OR solar panels OR HVAC OR home remodel OR pest control OR water damage restoration",
        "strong": [
            "solar panels", "solar installation", "rooftop solar", "solar tax credit",
            "roof", "roofing", "shingles", "roof repair", "roof replacement",
            "storm damage", "hail damage", "hvac", "air conditioning", "furnace",
            "heat pump", "ac repair", "water damage", "flood damage",
            "mold remediation", "foundation repair", "foundation crack",
            "window replacement", "replacement windows", "door installation",
            "bathroom remodel", "bathroom renovation", "shower remodel",
            "home renovation", "home improvement", "kitchen remodel",
            "kitchen renovation", "cabinet replacement", "pest control",
            "exterminator", "termite", "bed bugs", "tree removal", "tree service",
            "stump removal", "gutter installation", "gutter guards",
            "home security", "security system", "security cameras", "plumbing",
            "plumber", "burst pipe", "water heater", "sewer line", "frozen pipes",
        ],
        "weak": ["solar", "panels", "hail", "attic", "heating", "cooling",
                 "flooding", "leak", "mold", "basement", "foundation", "windows",
                 "doors", "bathroom", "shower", "kitchen", "cabinets",
                 "remodeling", "renovation", "pests", "trees", "gutters",
                 "security", "cameras", "pipe", "drain"],
    },
    "health_supplements": {
        "label": "Health & Supplements",
        "query": "weight loss OR diabetes OR testosterone OR hearing aids OR joint pain OR supplements",
        "strong": [
            "memory supplement", "brain supplement", "nootropics",
            "cognitive decline", "joint pain", "arthritis", "joint supplement",
            "knee pain", "hearing aid", "hearing aids", "hearing loss",
            "diabetes", "blood sugar", "type 2 diabetes", "glucose", "a1c",
            "weight loss", "lose weight", "fat loss", "glp-1", "ozempic",
            "men's health", "erectile dysfunction", "ed treatment",
            "testosterone", "low testosterone", "trt", "hair loss",
            "hair regrowth", "balding", "sleep supplement", "insomnia",
            "melatonin", "vision supplement", "eye health", "macular",
            "gut health", "probiotics", "microbiome",
        ],
        "weak": ["memory", "cognitive", "brain", "pain", "inflammation",
                 "mobility", "hearing", "ears", "insulin", "sugar", "diet",
                 "obesity", "metabolism", "libido", "hair", "scalp", "sleep",
                 "fatigue", "vision", "eyes", "gut", "digestion"],
    },
    "financial_publishing": {
        "label": "Financial Publishing & Investing",
        "query": "stock market OR cryptocurrency OR gold investing OR retirement planning OR dividend stocks",
        "strong": [
            "stock picks", "stock newsletter", "best stocks to buy",
            "cryptocurrency", "bitcoin", "crypto", "ethereum", "altcoin",
            "options trading", "covered calls", "retirement planning", "401k",
            "ira", "retirement income", "gold investing", "gold ira",
            "precious metals", "silver investing", "wealth preservation",
            "asset protection", "estate planning", "dividend stocks",
            "income investing", "high yield",
        ],
        "weak": ["stocks", "market", "investing", "portfolio", "blockchain",
                 "digital assets", "options", "trading", "retirement", "savings",
                 "pension", "gold", "silver", "bullion", "inflation hedge",
                 "wealth", "assets", "dividends", "yield", "passive income"],
    },
    "education_career": {
        "label": "Education & Career",
        "query": "online degree OR coding bootcamp OR nursing school OR trade school OR CDL training",
        "strong": [
            "coding bootcamp", "learn to code", "programming course",
            "ai course", "machine learning course", "generative ai training",
            "cybersecurity training", "security certification", "online degree",
            "online college", "degree program", "trade school",
            "vocational training", "nursing program", "nursing school",
            "rn program", "cdl training", "truck driving school", "cdl license",
        ],
        "weak": ["coding", "developer", "programming", "artificial intelligence",
                 "ai skills", "certification", "degree", "college", "tuition",
                 "trades", "vocational", "nursing", "nurse", "trucking", "driver"],
    },
    "b2b": {
        "label": "B2B Lead Gen",
        "query": "business software OR CRM OR payment processing OR managed IT services",
        "strong": [
            "saas", "software platform", "cloud software", "crm software",
            "customer relationship management", "sales crm", "accounting services",
            "bookkeeping", "accounting software", "merchant processing",
            "payment processing", "credit card processing", "hr software",
            "payroll software", "it services", "managed it", "msp",
            "cybersecurity services", "managed security", "threat detection",
        ],
        "weak": ["software", "platform", "subscription", "crm", "sales",
                 "pipeline", "accounting", "bookkeeper", "payments",
                 "transactions", "payroll", "onboarding", "technology",
                 "infrastructure", "cybersecurity", "breach", "threats"],
    },
}

NICHE_MATCH_THRESHOLD = float(os.environ.get("NICHE_MATCH_THRESHOLD", "0.3"))

# --- News sources (multi-source fetching) -----------------------------------
USE_GOOGLE_NEWS = os.environ.get("USE_GOOGLE_NEWS", "1") == "1"
USE_PUBLISHER_RSS = os.environ.get("USE_PUBLISHER_RSS", "1") == "1"
MAX_PER_FEED = int(os.environ.get("MAX_PER_FEED", "15"))

PUBLISHER_FEEDS = [
    ("https://www.cnbc.com/id/10000115/device/rss/rss.html", "CNBC Real Estate"),
    ("https://www.cnbc.com/id/10000664/device/rss/rss.html", "CNBC Finance"),
    ("https://finance.yahoo.com/news/rssindex",              "Yahoo Finance"),
    ("https://feeds.npr.org/1006/rss.xml",                   "NPR Business"),
    ("https://www.housingwire.com/feed/",                    "HousingWire"),
    ("https://www.insurancejournal.com/news/national/feed/", "Insurance Journal"),
    ("https://www.investing.com/rss/news_285.rss",           "Investing.com"),
]

NEWSDATA_API_KEY = os.environ.get("NEWSDATA_API_KEY", "").strip()