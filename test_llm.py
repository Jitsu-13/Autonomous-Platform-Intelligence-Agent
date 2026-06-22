"""
Quick connectivity test for configured LLM provider + Linear API key.
Usage: python test_llm.py
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

PASS = "[PASS]"
FAIL = "[FAIL]"
SKIP = "[SKIP]"


def test_openai():
    print("\n--- OpenAI ---")
    key = os.getenv("OPENAI_API_KEY", "")
    if not key or key == "sk-...":
        print(f"{SKIP} OPENAI_API_KEY not set")
        return None

    print(f"  Key prefix : {key[:12]}...")
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=16,
            messages=[
                {"role": "system", "content": "You are a test assistant."},
                {"role": "user",   "content": "Reply with the single word: working"},
            ],
        )
        reply  = response.choices[0].message.content.strip()
        tokens = response.usage.total_tokens
        print(f"  Model      : {response.model}")
        print(f"  Response   : {reply!r}")
        print(f"  Tokens used: {tokens}")
        print(f"{PASS} OpenAI API key is valid")
        return True
    except Exception as e:
        print(f"{FAIL} {type(e).__name__}: {e}")
        return False


def test_anthropic():
    print("\n--- Anthropic (Claude) ---")
    key = os.getenv("ANTHROPIC_API_KEY", "")
    if not key or key == "sk-ant-...":
        print(f"{SKIP} ANTHROPIC_API_KEY not set")
        return None

    print(f"  Key prefix : {key[:12]}...")
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=16,
            messages=[{"role": "user", "content": "Reply with the single word: working"}],
        )
        reply  = response.content[0].text.strip()
        tokens = response.usage.input_tokens + response.usage.output_tokens
        print(f"  Model      : {response.model}")
        print(f"  Response   : {reply!r}")
        print(f"  Tokens used: {tokens}")
        print(f"{PASS} Anthropic API key is valid")
        return True
    except Exception as e:
        print(f"{FAIL} {type(e).__name__}: {e}")
        return False


def test_active_provider():
    print("\n--- Active LLM Provider ---")
    try:
        from agent.llm.provider import get_provider, complete
        provider = get_provider()
        print(f"  Provider   : {provider}")
        response = complete(
            system="You are a test assistant.",
            user="Reply with the single word: working",
            max_tokens=16,
            fast=True,
        )
        print(f"  Model      : {response.model}")
        print(f"  Response   : {response.text!r}")
        print(f"  Tokens used: {response.tokens_used}")
        print(f"{PASS} Agent LLM provider is working")
        return True
    except Exception as e:
        print(f"{FAIL} {type(e).__name__}: {e}")
        return False


def test_linear():
    print("\n--- Linear API ---")
    key = os.getenv("LINEAR_API_KEY", "")
    if not key or key == "lin_api_...":
        print(f"{SKIP} LINEAR_API_KEY not set")
        return None

    print(f"  Key prefix : {key[:12]}...")
    try:
        import httpx
        response = httpx.post(
            "https://api.linear.app/graphql",
            json={"query": "{ viewer { id name email } }"},
            headers={"Authorization": key, "Content-Type": "application/json"},
            timeout=15,
        )
        body = response.json()
        if "errors" in body:
            msg = body["errors"][0].get("message", "unknown error")
            print(f"{FAIL} GraphQL error: {msg}")
            return False

        viewer = body.get("data", {}).get("viewer", {})
        print(f"  Workspace  : {viewer.get('name', 'unknown')} ({viewer.get('email', '')})")
        print(f"{PASS} Linear API key is valid")
        return True
    except Exception as e:
        print(f"{FAIL} {type(e).__name__}: {e}")
        return False


def test_linear_team():
    print("\n--- Linear Team ID (optional) ---")
    team_id = os.getenv("LINEAR_TEAM_ID", "")
    if not team_id:
        print("  LINEAR_TEAM_ID not set — agent will use first available team")
        return True

    key = os.getenv("LINEAR_API_KEY", "")
    if not key or key == "lin_api_...":
        print(f"{SKIP} LINEAR_API_KEY not set, skipping team check")
        return None

    try:
        import httpx
        response = httpx.post(
            "https://api.linear.app/graphql",
            json={"query": "{ teams { nodes { id key name } } }"},
            headers={"Authorization": key, "Content-Type": "application/json"},
            timeout=15,
        )
        teams = response.json().get("data", {}).get("teams", {}).get("nodes", [])
        match = next((t for t in teams if t["key"] == team_id or t["id"] == team_id), None)
        if match:
            print(f"  Found team : {match['name']} (key: {match['key']}, id: {match['id']})")
            print(f"{PASS} LINEAR_TEAM_ID resolved correctly")
        else:
            keys = [t["key"] for t in teams]
            print(f"  WARNING: '{team_id}' not found. Available: {keys}")
        return True
    except Exception as e:
        print(f"{FAIL} {type(e).__name__}: {e}")
        return False


if __name__ == "__main__":
    print("=" * 48)
    print("  API Key Connectivity Test")
    print("=" * 48)

    openai_result     = test_openai()
    anthropic_result  = test_anthropic()
    provider_result   = test_active_provider()
    linear_result     = test_linear()
    _                 = test_linear_team()

    llm_ok = (openai_result is True) or (anthropic_result is True)

    print("\n" + "=" * 48)
    if llm_ok and linear_result is True and provider_result is True:
        print("  All checks passed. Ready to run the agent.")
        print(f"  Active provider: {os.getenv('LLM_PROVIDER', 'auto-detected')}")
    else:
        if not llm_ok:
            print("  No working LLM key found (need OpenAI or Anthropic).")
        if linear_result is not True:
            print("  Linear API key check failed.")
        if provider_result is not True:
            print("  Agent provider layer failed.")
    print("=" * 48)
    sys.exit(0 if (llm_ok and linear_result is True and provider_result is True) else 1)
