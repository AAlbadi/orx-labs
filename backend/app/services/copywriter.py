"""
SynapseCopywriter — Generates hyper-personalized B2B outreach emails.

Uses OpenRouter free-tier LLM (llama-3.3-70b) to write cold emails grounded
in the prospect's real harvested context (LinkedIn, GitHub, arXiv).

No fallback templates — if the LLM fails, the job raises so we can retry.
"""
import json
import requests
from backend.app.config import settings

FREE_MODEL = "google/gemma-4-31b-it:free"
FALLBACK_MODEL = "openai/gpt-oss-20b:free"

FREE_MODELS = [
    "google/gemma-4-31b-it:free",
    "openai/gpt-oss-120b:free",
    "openai/gpt-oss-20b:free",
    "nousresearch/hermes-3-llama-3.1-405b:free",
]

BANNED_WORDS = [
    "delve", "testament", "hope this email finds you well",
    "excited to reach out", "moreover", "furthermore",
    "tapestry", "in summary", "underscores", "paradigm",
    "revolutionary", "groundbreaking", "beacon", "synergy",
    "leverage", "delighted", "I came across your profile",
    "I was impressed by", "cutting-edge", "seamlessly",
]


class SynapseCopywriter:
    def __init__(self):
        self.key = settings.OPENROUTER_API_KEY
        self.model = FREE_MODEL

    def generate_copy(self, lead_info: dict, context: dict, variant: str = "A") -> tuple[str, str]:
        """
        Generate a personalized email (subject, body) using the LLM.
        Raises RuntimeError if generation fails so the pipeline can surface the error.
        """
        if not self.key:
            raise RuntimeError("OPENROUTER_API_KEY is not set — cannot generate copy.")

        first_name = lead_info.get("first_name", "")
        last_name = lead_info.get("last_name", "")
        company = lead_info.get("company", "")
        role = lead_info.get("role", "")

        # ── Build context block based on variant ──────────────────────────
        context_lines = []

        linkedin = context.get("linkedin", {})
        if linkedin.get("summary"):
            context_lines.append(f"LinkedIn summary: {linkedin['summary']}")
        if linkedin.get("recent_posts"):
            posts = linkedin["recent_posts"]
            if isinstance(posts, list) and posts:
                context_lines.append(f"Their recent post: \"{posts[0]}\"")

        github = context.get("github", [])
        if github:
            top = github[0]
            context_lines.append(
                f"GitHub top repo: {top['name']} ({top.get('language','')}, ⭐{top.get('stars',0)}) — {top.get('description','')}"
            )

        pubs = context.get("publications", [])
        if pubs:
            context_lines.append(f"Recent paper: \"{pubs[0]['title']}\"")

        if variant == "A":
            focus = (
                "Focus the opening hook on their GitHub work or academic research. "
                "Make it feel like a peer-to-peer technical conversation, not a pitch."
            )
        else:
            focus = (
                "Focus the opening hook on their recent LinkedIn activity or professional role. "
                "Make it feel like a warm, direct introduction — not a sales email."
            )

        context_block = "\n".join(context_lines) if context_lines else "No specific public context available — write a concise, general outreach."

        system_prompt = (
            "You are a world-class B2B sales copywriter specializing in cold email to technical founders and engineers.\n"
            "Rules:\n"
            f"- NEVER use: {', '.join(BANNED_WORDS)}\n"
            "- Keep the email under 100 words total (not counting subject)\n"
            "- Open with a highly specific hook grounded in their actual work\n"
            "- No generic openers. No 'I hope this finds you well'. No marketing speak.\n"
            "- Sign off as: Abdu Aziz (Founder, ORX)\n"
            "- Output ONLY valid JSON: {\"subject\": \"...\", \"body\": \"...\"}\n"
            "- No markdown. No code fences. Raw JSON only."
        )

        user_prompt = (
            f"Prospect: {first_name} {last_name}, {role} at {company}\n"
            f"Context from their public profile:\n{context_block}\n\n"
            f"Variant instruction: {focus}\n\n"
            "Write the personalized outreach email now."
        )

        result = self._call_openrouter(system_prompt, user_prompt)
        if not result:
            raise RuntimeError(f"OpenRouter returned no content for {first_name} {last_name}")

        # Parse JSON
        try:
            # Strip any accidental markdown fences
            clean = result.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            parsed = json.loads(clean)
            subject = parsed.get("subject", "").strip()
            body = parsed.get("body", "").strip()
            if not subject or not body:
                raise ValueError("Empty subject or body in LLM response")
            return subject, body
        except Exception as e:
            raise RuntimeError(f"Failed to parse LLM copywriting response: {e}\nRaw: {result[:500]}")

    def _call_openrouter(self, system: str, user: str) -> str | None:
        for model in FREE_MODELS:
            try:
                resp = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://orx-outreach.ai",
                        "X-Title": "ORX Outreach Engine",
                    },
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": user},
                        ],
                        "temperature": 0.65,
                        "max_tokens": 512,
                        "response_format": {"type": "json_object"},
                    },
                    timeout=40,
                )
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"]
                err = resp.json().get("error", {}).get("message", "")
                if "429" in str(resp.status_code) or "rate" in err.lower() or "provider" in err.lower():
                    print(f"[Copywriter] {model} unavailable, trying next model...")
                    import time; time.sleep(1)
                    continue
                print(f"[Copywriter] {model} error {resp.status_code}: {err[:200]}")
                return None
            except Exception as e:
                print(f"[Copywriter] {model} request failed: {e}")
        print("[Copywriter] All free models exhausted.")
        return None


copywriter = SynapseCopywriter()
