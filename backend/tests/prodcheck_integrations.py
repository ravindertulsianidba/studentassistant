"""Ad-hoc production-readiness integration checks (sanitized output; no secrets printed)."""
import os, ssl, smtplib
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

def mask(ok): return "PASS" if ok else "FAIL"

# 1) Live OpenAI request
def check_openai():
    try:
        import httpx
        key = os.environ["OPENAI_API_KEY"]
        model = os.environ.get("OPENAI_MODEL_JSON", "gpt-4o-mini")
        r = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json={"model": model, "messages": [{"role": "user", "content": "Reply with the single word OK."}], "max_tokens": 5},
            timeout=30,
        )
        if r.status_code == 200:
            txt = r.json()["choices"][0]["message"]["content"].strip()
            return True, f"HTTP 200, model={model}, reply='{txt[:20]}'"
        return False, f"HTTP {r.status_code}: {r.text[:160]}"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:160]}"

# 2) SMTP login (real handshake + AUTH, no email content)
def check_smtp():
    host = os.environ.get("SMTP_HOST"); port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USERNAME"); pw = os.environ.get("SMTP_PASSWORD")
    try:
        s = smtplib.SMTP(host, port, timeout=30)
        s.ehlo(); s.starttls(context=ssl.create_default_context()); s.ehlo()
        s.login(user, pw)
        s.quit()
        return True, f"connected+AUTH ok to {host}:{port} as {user}"
    except Exception as e:
        return False, f"{type(e).__name__}: {str(e)[:200]}"

if __name__ == "__main__":
    o_ok, o_msg = check_openai()
    print(f"[OpenAI]  {mask(o_ok)} — {o_msg}")
    s_ok, s_msg = check_smtp()
    print(f"[SMTP]    {mask(s_ok)} — {s_msg}")
