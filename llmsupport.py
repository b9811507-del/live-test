#!/usr/bin/env python3
"""llmsupport — shared multi-provider LLM client with fallback chain.
Providers tried in order (first success wins): Groq -> OpenRouter -> Mistral -> Gemini1 -> Gemini2.
Env keys: GROQ_API_KEY, OPENROUTER_API_KEY, MISTRAL_API_KEY, GEMINI_API_KEY, GEMINI_API_KEY2.
Used by paidbot (admin AI chat) and GitHub agents (error analysis/fix). Stdlib only.
"""
import os, json, re, time

_TIMEOUT = 35

def _post(url, hdr, body, timeout=_TIMEOUT):
    import urllib.request
    hdr = {**hdr, "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) live-agri-bot/1.0"}
    rq = urllib.request.Request(url, data=json.dumps(body).encode(), headers=hdr)
    r = json.loads(urllib.request.urlopen(rq, timeout=timeout).read())
    return r

def _openai_base(key, base, model, system, user, max_tok, timeout):
    r = _post(f"{base}/chat/completions",
              {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
              {"model": model, "max_tokens": max_tok,
               "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
              timeout)
    return r["choices"][0]["message"]["content"]

def _gemini(key, model, system, user, max_tok, timeout):
    r = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}",
              {"Content-Type": "application/json"},
              {"systemInstruction": {"parts": [{"text": system}]},
               "contents": [{"parts": [{"text": user}]}],
               "generationConfig": {"maxOutputTokens": max_tok}}, timeout)
    return r["candidates"][0]["content"]["parts"][0]["text"]

def providers():
    """(name, callable) chain — keys read live so env-only setup works."""
    P = []
    if os.environ.get("GROQ_API_KEY"):
        P.append(("groq", lambda s, u, m: _openai_base(os.environ["GROQ_API_KEY"],
            "https://api.groq.com/openai/v1", "openai/gpt-oss-120b", s, u, m, 40)))
    if os.environ.get("OPENROUTER_API_KEY"):
        P.append(("openrouter", lambda s, u, m: _openai_base(os.environ["OPENROUTER_API_KEY"],
            "https://openrouter.ai/api/v1", "meta-llama/llama-3.3-70b-instruct", s, u, m, 50)))
    if os.environ.get("MISTRAL_API_KEY"):
        P.append(("mistral", lambda s, u, m: _openai_base(os.environ["MISTRAL_API_KEY"],
            "https://api.mistral.ai/v1", "mistral-small-latest", s, u, m, 40)))
    for e in ("GEMINI_API_KEY", "GEMINI_API_KEY2"):
        if os.environ.get(e):
            P.append((e, (lambda kk: lambda s, u, m: _gemini(os.environ[kk], "gemini-3.6-flash", s, u, m, 40))(e)))
    return P

def ask(system, user, max_tokens=1200):
    """Try each provider; return text. None if all fail."""
    for name, fn in providers():
        for attempt in (0, 1):
            try:
                out = fn(system, user, max_tokens)
                if out and out.strip():
                    return out.strip()
            except Exception as e:
                if attempt == 0 and "429" in str(e):
                    time.sleep(4); continue
            break
    return None

def try_json(text):
    """Extract first JSON object from model output (handles fences / surrounding prose)."""
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    cand = m.group(1) if m else None
    if cand is None:
        i = text.find("{"); j = text.rfind("}")
        cand = text[i:j + 1] if i != -1 and j > i else None
    if cand is None:
        return None
    for c in (cand, cand.replace("\n", " ")):
        try:
            return json.loads(c)
        except Exception:
            pass
    return None

if __name__ == "__main__":
    out = ask("You are a terse test bot.", "reply with exactly: OK")
    print("LLM:", out[:60] if out else None)
