"""
Minimal Gemini (free tier) REST client. No SDK, no heavy deps -- just requests.

If no API key is set, every call returns None and the correlator falls back to
a safe template. So the whole project still runs with zero keys.
"""
import json
import requests

from config import GEMINI_API_KEY, GEMINI_ENDPOINT, GEMINI_MODEL


def available() -> bool:
    return bool(GEMINI_API_KEY)


def generate_json(prompt: str, timeout: int = 30) -> dict | None:
    """Call Gemini and parse a JSON object out of the response. None on failure."""
    if not GEMINI_API_KEY:
        return None
    try:
        resp = requests.post(
            GEMINI_ENDPOINT,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": GEMINI_API_KEY,
            },
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.7,
                    "responseMimeType": "application/json",
                },
            },
            timeout=timeout,
        )
        if resp.status_code != 200:
            print(f"[gemini] HTTP {resp.status_code}: {resp.text[:200]}")
            return None
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return _extract_json(text)
    except (requests.RequestException, KeyError, IndexError, ValueError) as e:
        print(f"[gemini] call failed: {e}")
        return None


def generate_text(prompt: str, timeout: int = 30) -> str | None:
    """Plain-text Gemini call (scene prompts + video scripts). None on failure."""
    if not GEMINI_API_KEY:
        return None
    try:
        resp = requests.post(
            GEMINI_ENDPOINT,
            headers={"Content-Type": "application/json", "x-goog-api-key": GEMINI_API_KEY},
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"temperature": 0.8}},
            timeout=timeout,
        )
        if resp.status_code != 200:
            print(f"[gemini] HTTP {resp.status_code}: {resp.text[:200]}")
            return None
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except (requests.RequestException, KeyError, IndexError, ValueError) as e:
        print(f"[gemini] text call failed: {e}")
        return None
    
def _extract_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
    return None


if __name__ == "__main__":
    print("Gemini key present:", available(), "| model:", GEMINI_MODEL)
    if available():
        print(generate_json('Return JSON: {"ok": true, "msg": "hello"}'))
