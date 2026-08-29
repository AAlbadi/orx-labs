import asyncio
import logging
import re
import os
import subprocess
import json
from typing import Optional, Dict, Any, List
import httpx
import websockets

logger = logging.getLogger(__name__)

class ChromeApolloService:
    def __init__(self, cdp_url: str = "http://127.0.0.1:9222"):
        self.cdp_url = cdp_url
        self.req_id = 0

    def _next_id(self) -> int:
        self.req_id += 1
        return self.req_id

    async def check_connection(self) -> Dict[str, Any]:
        """Checks if Chrome is running with CDP enabled on port 9222."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get(f"{self.cdp_url}/json/version")
                if res.status_code == 200:
                    return {
                        "connected": True,
                        "info": res.json()
                    }
        except Exception:
            pass
        return {
            "connected": False,
            "error": "Chrome is not connected on port 9222."
        }

    async def ensure_chrome_running(self) -> bool:
        """
        Ensures Chrome is running with remote debugging port 9222.
        Uses the user's Chrome Profile with LinkedIn + Apollo logged in.
        """
        status = await self.check_connection()
        if status.get("connected"):
            return True

        logger.info("Chrome not detected on port 9222. Auto-launching with user profile...")
        chrome_bin = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        home = os.path.expanduser("~")
        user_data_dir = os.path.join(home, "Library/Application Support/Google/Chrome")
        profile_name = "Profile 1"
        ext_path = os.path.join(home, "Library/Application Support/Google/Chrome/Profile 1/Extensions/alhgpfoeiimagjlnfekdhkjlkiomcapa/16.5.0_0")

        try:
            cmd = [
                chrome_bin if os.path.exists(chrome_bin) else "google-chrome",
                "--remote-debugging-port=9222",
                f"--user-data-dir={user_data_dir}",
                f"--profile-directory={profile_name}",
                f"--load-extension={ext_path}",
                "--disable-features=IsolateOrigins,site-per-process",
                "--no-first-run",
                "--no-default-browser-check",
                "https://www.linkedin.com"
            ]

            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            # Wait for Chrome CDP port to become active
            for _ in range(20):
                await asyncio.sleep(0.5)
                status = await self.check_connection()
                if status.get("connected"):
                    logger.info("🟢 Chrome auto-launched and connected on port 9222!")
                    return True
        except Exception as e:
            logger.error(f"Failed to auto-launch Chrome: {e}")

        return False

    async def _get_or_create_page(self, target_url: str) -> tuple[str, str]:
        """Returns (tab_id, ws_url). Reuses existing LinkedIn tab or creates new one."""
        async with httpx.AsyncClient(timeout=5.0) as client:
            res = await client.get(f"{self.cdp_url}/json")
            pages = [p for p in res.json() if p.get("type") == "page"]
            
            for p in pages:
                if "linkedin.com" in p.get("url", "") or p.get("url") == "about:blank":
                    return p["id"], p["webSocketDebuggerUrl"]
            
            # Create new tab
            new_res = await client.put(f"{self.cdp_url}/json/new?{target_url}")
            data = new_res.json()
            return data["id"], data["webSocketDebuggerUrl"]

    async def _evaluate_js(self, ws, expression: str, timeout_sec: float = 16.0) -> Any:
        msg_id = self._next_id()
        payload = {
            "id": msg_id,
            "method": "Runtime.evaluate",
            "params": {
                "expression": expression,
                "awaitPromise": True,
                "returnByValue": True
            }
        }
        await ws.send(json.dumps(payload))
        
        while True:
            msg = await asyncio.wait_for(ws.recv(), timeout=timeout_sec)
            data = json.loads(msg)
            if data.get("id") == msg_id:
                res = data.get("result", {}).get("result", {})
                return res.get("value")

    async def extract_lead_with_apollo(self, profile_url: str, yield_log=None) -> Dict[str, Any]:
        """
        Navigates to the given LinkedIn profile URL in Chrome via direct CDP,
        triggers the Apollo.io Chrome extension, clicks 'Access email',
        and extracts the revealed email, phone, and profile details.
        """
        async def log(msg: str):
            if yield_log:
                await yield_log(msg)
            logger.info(msg)

        await self.ensure_chrome_running()

        try:
            tab_id, ws_url = await self._get_or_create_page(profile_url)
        except Exception as e:
            await log(f"⚠️ Cannot connect to Chrome tab: {e}")
            return {"name": "Prospect", "linkedin_url": profile_url, "email": None, "phone": None}

        try:
            async with websockets.connect(ws_url, ping_interval=None) as ws:
                # Enable required CDP domains
                await ws.send(json.dumps({"id": self._next_id(), "method": "Page.enable"}))
                await ws.send(json.dumps({"id": self._next_id(), "method": "Runtime.enable"}))
                
                # Navigate to the target LinkedIn URL
                await log(f"🌐 Navigating to {profile_url}...")
                await ws.send(json.dumps({
                    "id": self._next_id(),
                    "method": "Page.navigate",
                    "params": {"url": profile_url}
                }))

                # Wait for initial LinkedIn page render & Apollo sidebar mount
                await asyncio.sleep(3.0)

                # 1. Extract Profile DOM info from LinkedIn
                dom_extract_js = """
                (() => {
                    const getTxt = (sel) => {
                        const el = document.querySelector(sel);
                        return el ? el.innerText.trim() : '';
                    };
                    
                    let rawName = getTxt('h1.text-heading-xlarge') || 
                                  getTxt('h1.inline.t-24.v-align-middle') || 
                                  getTxt('h1') || 
                                  document.title.split('|')[0].replace('- LinkedIn', '').trim();
                    
                    // Strip notification count e.g. (22)
                    let name = rawName.replace(/^\\(\\d+\\)\\s*/, '').replace(/\\(.*?\\)/g, '').trim();
                    if (!name) name = rawName.replace(/^\\(\\d+\\)\\s*/, '').trim();
                    
                    let headline = getTxt('div.text-body-medium.break-words') || 
                                   getTxt('.pv-text-details__left-panel div.text-body-medium') || 
                                   getTxt('.pv-top-card--list-bullet li') || '';
                    
                    let location = getTxt('span.text-body-small.inline.t-black--light.break-words') || 
                                   getTxt('.pv-text-details__left-panel .text-body-small') || '';

                    let company = getTxt('button[aria-label*="Current company"]') || 
                                  getTxt('.pv-text-details__right-panel li') || 
                                  getTxt('div[aria-label="Current company"]') || '';

                    if (!company && headline.includes(' at ')) {
                        company = headline.split(' at ').pop().split('·')[0].split('|')[0].trim();
                    } else if (!company && headline.includes(' @ ')) {
                        company = headline.split(' @ ').pop().split('·')[0].split('|')[0].trim();
                    }

                    return { name, headline, location, company };
                })()
                """
                profile_info = await self._evaluate_js(ws, dom_extract_js) or {}
                if profile_info.get("name"):
                    await log(f"👤 Profile: {profile_info.get('name')} — {profile_info.get('company') or profile_info.get('headline') or 'Identified'}")

                # 2. Interact with Apollo Extension (Sidepanel / Dock / Access email button)
                apollo_interaction_js = r"""
                (async () => {
                    const sleep = (ms) => new Promise(r => setTimeout(r, ms));
                    
                    function queryAllDeep(selector, root = document) {
                        let results = Array.from(root.querySelectorAll(selector));
                        const allEls = root.querySelectorAll('*');
                        for (const el of allEls) {
                            if (el.shadowRoot) {
                                results = results.concat(queryAllDeep(selector, el.shadowRoot));
                            }
                        }
                        return results;
                    }

                    // Check if Apollo panel is collapsed & click dock icon if needed
                    const triggers = queryAllDeep('#apollo-extension-trigger, div[data-cy="apollo-trigger"], .apollo-sidebar-toggle, button[aria-label*="Apollo"], [class*="apollo"]');
                    for (const t of triggers) {
                        if (t.offsetWidth > 0 && t.offsetHeight > 0) {
                            t.click();
                            break;
                        }
                    }
                    
                    await sleep(1500);

                    const emailPattern = /[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+/g;
                    const cleanEmail = (list) => {
                        return (list || []).filter(e => {
                            const low = e.toLowerCase();
                            return !low.includes('apollo.io') && 
                                   !low.includes('linkedin.com') && 
                                   !low.includes('google.com') && 
                                   !low.includes('sentry.io') &&
                                   !low.includes('example.com');
                        });
                    };

                    // Check if email already revealed
                    let bodyText = document.body ? document.body.innerText : '';
                    let foundEmails = cleanEmail(bodyText.match(emailPattern));
                    if (foundEmails.length > 0) {
                        return { email: foundEmails[0], status: 'Already Unlocked', unlocked: true };
                    }

                    // Click 'Access email' or 'Access work email' button
                    const allButtons = queryAllDeep('button, div[role="button"], a');
                    let clicked = false;
                    for (const btn of allButtons) {
                        const txt = (btn.innerText || btn.textContent || '').trim().toLowerCase();
                        if (txt === 'access email' || 
                            txt === 'access work email' || 
                            txt === 'access email & phone' || 
                            txt.includes('access email')) {
                            btn.click();
                            clicked = true;
                            break;
                        }
                    }

                    if (clicked) {
                        // Poll for revealed email
                        for (let i = 0; i < 15; i++) {
                            await sleep(500);
                            bodyText = document.body ? document.body.innerText : '';
                            foundEmails = cleanEmail(bodyText.match(emailPattern));
                            if (foundEmails.length > 0) {
                                return { email: foundEmails[0], status: 'Unlocked', unlocked: true, clicked: true };
                            }
                        }
                    }

                    return { email: null, status: clicked ? 'Clicked Waiting' : 'No Email', unlocked: false, clicked };
                })()
                """
                apollo_res = await self._evaluate_js(ws, apollo_interaction_js) or {}

                email = apollo_res.get("email")
                if email:
                    await log(f"🎉 Successfully unlocked email: {email}")
                else:
                    await log("ℹ️ Email not available in Apollo for this prospect")

                return {
                    **profile_info,
                    "email": email,
                    "phone": apollo_res.get("phone"),
                    "apollo_unlocked": bool(email),
                    "linkedin_url": profile_url
                }

        except Exception as e:
            await log(f"⚠️ Profile check notice for {profile_url}: {e}")
            return {
                "name": "Prospect",
                "linkedin_url": profile_url,
                "email": None,
                "phone": None,
                "status": "Found",
                "error": str(e)
            }

    async def close(self):
        pass
