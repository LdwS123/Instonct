"""Drives the real Chromium of the remote screen (Chrome DevTools Protocol), with the same calls as webagent.Browser.

Why: Lightpanda is light but has its own cookies and big shops turn it away. Here the bot works in the very window the user can open on their phone,
so a cart filled by the bot is there when they take over to pay. Nothing tries to hide that this is a program: on a security check the bot stops and hands over.
"""

import json
import time

import requests

from . import screen

PORT = screen.DEBUG_PORT
MINUTES = 45
LOAD_WAIT = 20

_PAGE_TEXT = "(()=>{const b=document.body;return (document.title?('# '+document.title+'\\n\\n'):'')+(b?b.innerText:'')})()"
_ELEMENTS = """(()=>{let n=0;const out=[];
document.querySelectorAll('[data-bot]').forEach(e=>e.removeAttribute('data-bot'));
for(const e of document.querySelectorAll('a[href],button,input,select,textarea,[role=button],[role=link],[role=checkbox],[onclick]')){
 const r=e.getBoundingClientRect();const type=(e.type||'').toLowerCase();
 if(type==='hidden'||(!r.width&&!r.height)||e.disabled)continue;
 n+=1;e.setAttribute('data-bot',String(n));
 const tag=e.tagName.toLowerCase();
 const role=e.getAttribute('role')||(tag==='a'?'link':tag==='button'?'button':'');
 const label=(e.labels&&e.labels[0]&&e.labels[0].innerText)||e.getAttribute('aria-label')||e.placeholder||e.innerText||e.value||e.name||'';
 out.push({tagName:tag,role:role,inputType:type,name:label.trim().slice(0,60),value:type==='password'?'':String(e.value||'').slice(0,30),selector:'[data-bot="'+n+'"]'});
}return JSON.stringify(out);})()"""
# QS = document.querySelector that also looks inside the shadow root of #interop-outlet, where LinkedIn draws its dialogs.
_QS = "const QS=(s)=>{let e=document.querySelector(s);if(!e){const o=document.querySelector('#interop-outlet');if(o&&o.shadowRoot)e=o.shadowRoot.querySelector(s);}return e;};"
_CENTER = """(()=>{""" + _QS + """const e=QS(%s);if(!e)return '';e.scrollIntoView({block:'center'});const r=e.getBoundingClientRect();
return JSON.stringify({x:r.left+r.width/2,y:r.top+r.height/2});})()"""
_LINKS = "JSON.stringify([...document.querySelectorAll('a[href]')].filter(a=>a.innerText.trim()).slice(0,%d).map(a=>({text:a.innerText.trim().slice(0,60),href:a.href})))"
_SELECT = """(()=>{const e=document.querySelector(%s);if(!e)return 'none';const v=%s;const o=[...e.options].find(o=>o.value===v||o.text.trim()===v);
if(!o)return 'none';e.value=o.value;e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));return 'ok';})()"""


class Stop(Exception):
    """The real browser cannot be used right now."""


class Browser:
    def _targets(self):
        return requests.get(f"http://127.0.0.1:{PORT}/json/list", timeout=3).json()

    def _ready(self):
        """Opens the screen if it is closed. The session stays when it is already open: that is the whole point."""
        try:
            pages = [t for t in self._targets() if t.get("type") == "page"]
            if pages:
                return pages[0]
        except (requests.RequestException, ValueError):
            pass
        r = screen.start(MINUTES, "about:blank")
        if not r.get("ok"):
            raise Stop(str(r.get("erreur", "l'ecran ne demarre pas")))
        end = time.time() + 15
        while time.time() < end:
            try:
                pages = [t for t in self._targets() if t.get("type") == "page"]
                if pages:
                    return pages[0]
            except (requests.RequestException, ValueError):
                pass
            time.sleep(0.4)
        raise Stop("le navigateur ne repond pas (si l'ecran etait deja ouvert avant cette version, fais /connexion stop)")

    def _send(self, method, timeout=30, **params):
        import websocket
        target = self._ready()
        ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=timeout, suppress_origin=True)
        try:
            ws.send(json.dumps({"id": 1, "method": method, "params": params}))
            while True:
                msg = json.loads(ws.recv())
                if msg.get("id") == 1:
                    if "error" in msg:
                        raise Stop(str(msg["error"].get("message", msg["error"]))[:200])
                    return msg.get("result", {})
        finally:
            ws.close()

    def js(self, script, timeout=30, **_):
        res = self._send("Runtime.evaluate", timeout=timeout, expression=script, returnByValue=True, awaitPromise=True)
        if "exceptionDetails" in res:
            raise Stop("erreur dans la page : " + str(res["exceptionDetails"].get("text", ""))[:150])
        value = res.get("result", {}).get("value", "")
        return value if isinstance(value, str) else json.dumps(value)

    def _settle(self):
        """Waits for the page to finish loading, then a moment for the scripts that draw it."""
        time.sleep(0.3)
        end = time.time() + LOAD_WAIT
        while time.time() < end:
            try:
                if self.js("document.readyState") == "complete":
                    break
            except Exception:
                pass
            time.sleep(0.3)
        time.sleep(0.8)

    def _point(self, selector):
        raw = self.js(_CENTER % json.dumps(selector))
        if not raw:
            raise Stop("element introuvable : utilise forms pour voir les boutons")
        return json.loads(raw)

    def _click(self, selector):
        at = self._point(selector)
        for kind in ("mousePressed", "mouseReleased"):
            self._send("Input.dispatchMouseEvent", type=kind, x=at["x"], y=at["y"], button="left", clickCount=1)

    def _key(self, key):
        special = {"Enter": ("\r", 13), "Tab": ("", 9), "Escape": ("", 27), "Backspace": ("", 8), "ArrowDown": ("", 40), "ArrowUp": ("", 38)}
        text, code = special.get(key, (key if len(key) == 1 else "", ord(key.upper()) if len(key) == 1 else 0))
        self._send("Input.dispatchKeyEvent", type="keyDown", key=key, code=key, windowsVirtualKeyCode=code, **({"text": text} if text else {}))
        self._send("Input.dispatchKeyEvent", type="keyUp", key=key, code=key, windowsVirtualKeyCode=code)

    def call(self, tool, timeout=60, **a):
        """Same names as the Lightpanda tools, so web.tool_browser and all its checks work unchanged."""
        if tool == "goto":
            self._send("Page.navigate", url=a["url"])
            self._settle()
            return ""
        if tool == "getUrl":
            return self.js("location.href")
        if tool == "markdown":
            return self.js(_PAGE_TEXT)[:int(a.get("maxBytes", 60000))]
        if tool == "interactiveElements":
            return self.js(_ELEMENTS)
        if tool == "links":
            return self.js(_LINKS % min(int(a.get("limit", 30)), 60))
        if tool == "click":
            self._click(a["selector"])
            self._settle()
            return ""
        if tool == "fill":
            self.js(f"(()=>{{{_QS}const e=QS({json.dumps(a['selector'])});e.focus();if(e.select)e.select();}})()")
            self._send("Input.insertText", text=a["value"])
            return ""
        if tool == "press":
            if a.get("selector"):
                self.js(f"(()=>{{{_QS}QS({json.dumps(a['selector'])}).focus();}})()")
            self._key(a["key"])
            self._settle()
            return ""
        if tool == "selectOption":
            if self.js(_SELECT % (json.dumps(a["selector"]), json.dumps(a["value"]))) != "ok":
                raise Stop("choix introuvable dans cette liste")
            return ""
        if tool == "setChecked":
            if (self.js(f"document.querySelector({json.dumps(a['selector'])}).checked") == "true") != a["checked"]:
                self._click(a["selector"])
            return ""
        if tool == "waitForSelector":
            end = time.time() + int(a.get("timeout", 8000)) / 1000
            while time.time() < end:
                if self.js(f"!!document.querySelector({json.dumps(a['selector'])})") == "true":
                    return ""
                time.sleep(0.3)
            raise Stop("element non trouve a temps")
        raise Stop(f"{tool} n'existe pas avec moteur=chrome : utilise read, ou le navigateur normal")

    def stop(self, kill=False):
        screen.stop()


DRIVER = Browser()
