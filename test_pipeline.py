#!/usr/bin/env python3
"""
ORX Real Pipeline Test — run from the project root:
  cd /Users/aziz/Documents/antigravity/zealous-faraday
  source backend/.venv/bin/activate
  python test_pipeline.py
"""
import sys, json, time, requests

BASE = "http://localhost:8000/api/v1"
BOLD  = "\033[1m"
GREEN = "\033[92m"
RED   = "\033[91m"
CYAN  = "\033[96m"
DIM   = "\033[2m"
RESET = "\033[0m"

def ok(msg): print(f"  {GREEN}✓{RESET} {msg}")
def fail(msg): print(f"  {RED}✗{RESET} {msg}"); 
def head(msg): print(f"\n{BOLD}{CYAN}── {msg} ──{RESET}")
def dim(msg): print(f"  {DIM}{msg}{RESET}")

errors = []

# ── 1. Health check ───────────────────────────────────────────────────────────
head("1. API Health")
try:
    r = requests.get(f"{BASE.replace('/api/v1','')}/", timeout=5)
    data = r.json()
    ok(f"API online — {data['app']} v{data['version']}")
except Exception as e:
    fail(f"API unreachable: {e}")
    print(f"\n{RED}Backend not running. Start it first:{RESET}")
    print("  cd backend && source .venv/bin/activate")
    print("  PYTHONPATH=.. uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload")
    sys.exit(1)

# ── 2. AI Lead Search (DDG + LLM) ────────────────────────────────────────────
head("2. Real Lead Search (DuckDuckGo + LLM)")
QUERY = "open source ML engineers at PyTorch"
print(f"  Query: \"{QUERY}\"")
print(f"  {DIM}(calling DuckDuckGo + OpenRouter LLM — takes ~20-40s…){RESET}")
t0 = time.time()
try:
    r = requests.post(f"{BASE}/leads/search",
        json={"query": QUERY}, timeout=90)
    elapsed = round(time.time() - t0, 1)
    data = r.json()
    if r.status_code == 200:
        count = data.get("leads_count", 0)
        ok(f"Found {count} real lead(s) in {elapsed}s")
        dim(data.get("message", ""))
        if count == 0:
            errors.append("Lead search returned 0 results — LLM may be rate-limited")
    else:
        fail(f"HTTP {r.status_code}: {data.get('detail','')}")
        errors.append("Lead search failed")
except Exception as e:
    fail(f"Search failed: {e}")
    errors.append(str(e))

# ── 3. Get current leads ──────────────────────────────────────────────────────
head("3. Leads in CRM")
try:
    r = requests.get(f"{BASE}/leads/", timeout=10)
    leads = r.json()
    ok(f"{len(leads)} total leads in database")

    for lead in leads[:3]:
        name = f"{lead.get('first_name','')} {lead.get('last_name','')}".strip()
        email = lead.get("email", "—")
        company = lead.get("company", "—")
        status = lead.get("status", "—")
        ctx = lead.get("harvested_context") or {}

        has_linkedin = bool(ctx.get("linkedin", {}).get("summary"))
        has_github   = len(ctx.get("github", [])) > 0
        has_pubs     = len(ctx.get("publications", [])) > 0

        signals = []
        if has_linkedin: signals.append("LinkedIn✓")
        if has_github:   signals.append(f"GitHub({len(ctx['github'])} repos)✓")
        if has_pubs:     signals.append(f"arXiv({len(ctx['publications'])} papers)✓")
        signals_str = "  ".join(signals) if signals else "no context yet"

        print(f"\n  {BOLD}{name}{RESET} <{email}>")
        dim(f"    {company}  •  status: {status}")
        dim(f"    signals: {signals_str}")
        if lead.get("personalized_subject"):
            dim(f"    email subject: \"{lead['personalized_subject']}\"")

    if len(leads) > 3:
        dim(f"    …and {len(leads)-3} more leads")
except Exception as e:
    fail(f"Could not fetch leads: {e}")
    errors.append(str(e))

# ── 4. GitHub API (real) ──────────────────────────────────────────────────────
head("4. GitHub API (live)")
try:
    import sys; sys.path.insert(0, "backend")
    from app.services.harvester import harvester
    repos = harvester._fetch_github_real("torvalds")
    if repos:
        ok(f"GitHub API: fetched {len(repos)} repos for @torvalds")
        for r in repos[:2]:
            dim(f"    {r['name']}  ({r['language']}, ⭐{r['stars']})")
    else:
        fail("GitHub API returned empty — check network")
        errors.append("GitHub API empty")
except Exception as e:
    fail(f"GitHub fetch error: {e}")
    errors.append(str(e))

# ── 5. arXiv API (real) ───────────────────────────────────────────────────────
head("5. arXiv API (live)")
try:
    papers = harvester._fetch_arxiv_real("Yann LeCun")
    if papers:
        ok(f"arXiv API: found {len(papers)} papers for 'Yann LeCun'")
        for p in papers[:2]:
            dim(f"    {p['title'][:65]}…")
    else:
        fail("arXiv returned no papers — may be a timeout")
        errors.append("arXiv empty")
except Exception as e:
    fail(f"arXiv fetch error: {e}")
    errors.append(str(e))

# ── 6. LLM Copywriting (real) ─────────────────────────────────────────────────
head("6. LLM Copywriting (OpenRouter free models)")
try:
    from app.services.copywriter import copywriter, FREE_MODELS
    print(f"  Model pool ({len(FREE_MODELS)} models):")
    for m in FREE_MODELS:
        dim(f"    • {m}")
    mock_context = {
        "linkedin": {
            "current_role": "Compiler Engineer",
            "company": "LLVM Foundation",
            "summary": "Lead contributor to LLVM's middle-end optimizations, specializing in loop vectorization.",
            "recent_posts": ["Just merged a 2x speedup on loop unrolling. Crazy what constant folding alone can do."],
        },
        "github": [{"name": "llvm-loop-opts", "language": "C++", "stars": 412, "description": "Loop optimization passes for LLVM"}],
        "publications": [],
    }
    subject, body = copywriter.generate_copy(
        lead_info={"first_name": "Chris", "last_name": "Lattner", "company": "LLVM Foundation", "role": "Compiler Engineer"},
        context=mock_context,
        variant="A",
    )
    ok(f"Copy generated ✓")
    dim(f"    Subject: \"{subject}\"")
    for line in body.split("\n")[:4]:
        if line.strip():
            dim(f"    {line}")
except Exception as e:
    fail(f"Copywriting failed: {e}")
    errors.append(str(e))

# ── 7. Analytics ──────────────────────────────────────────────────────────────
head("7. Analytics Dashboard")
try:
    r = requests.get(f"{BASE}/analytics/dashboard", timeout=10)
    data = r.json()
    summary = data.get("summary", {})
    ok(f"Analytics OK")
    dim(f"    Total: {summary.get('total_leads',0)} leads  •  Enriched: {summary.get('enriched_leads',0)}  •  Contacted: {summary.get('contacted_leads',0)}")
    dim(f"    Reply rate: {summary.get('reply_rate',0)}%  •  Meetings: {summary.get('meetings_booked',0)}")
except Exception as e:
    fail(f"Analytics failed: {e}")
    errors.append(str(e))

# ── Summary ───────────────────────────────────────────────────────────────────
print(f"\n{BOLD}{'─'*50}{RESET}")
if not errors:
    print(f"{GREEN}{BOLD}✓ All systems real and operational{RESET}")
else:
    print(f"{RED}{BOLD}⚠ {len(errors)} issue(s) found:{RESET}")
    for e in errors:
        print(f"  {RED}•{RESET} {e}")
print()
