"""
Запускается один раз для получения session string.
После получения SESSION_STRING задеплоить userbot.py
"""
import os
import asyncio
from aiohttp import web
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID   = 2496
API_HASH = "8da85b0d5bfe62527e5b244c209159c3"
PHONE    = os.environ.get("PHONE", "+79054761971")

pending = {}

HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>TG Auth</title>
<style>
body{font-family:sans-serif;max-width:400px;margin:80px auto;padding:20px;background:#1a1a2e;color:#eee}
input,button{width:100%;padding:12px;margin:8px 0;border-radius:8px;border:none;font-size:16px;box-sizing:border-box}
button{background:#5865f2;color:#fff;cursor:pointer;font-weight:bold}
button:hover{background:#4752c4}
.msg{padding:12px;border-radius:8px;margin:8px 0}
.ok{background:#2d7d46}.err{background:#8b1a1a}
pre{background:#0d1117;padding:16px;border-radius:8px;word-break:break-all;font-size:13px}
</style></head><body>
<h2>🔐 Telegram Auth</h2>
<div id="step1">
  <p>Нажми кнопку — придёт код в Telegram Denis:</p>
  <button onclick="requestCode()">Запросить код</button>
</div>
<div id="step2" style="display:none">
  <p>Введи код из Telegram:</p>
  <input id="code" placeholder="12345" maxlength="6">
  <button onclick="submitCode()">Войти</button>
</div>
<div id="step3" style="display:none">
  <div class="msg ok">✅ Готово! Скопируй session string в Railway Variables:</div>
  <p><b>SESSION_STRING =</b></p>
  <pre id="session"></pre>
  <button onclick="copySession()">📋 Скопировать</button>
</div>
<div id="msg"></div>
<script>
async function requestCode(){
  document.getElementById('msg').innerHTML='<div class="msg ok">Отправляю...</div>';
  const r=await fetch('/request_code',{method:'POST'});
  const d=await r.json();
  if(d.ok){
    document.getElementById('step1').style.display='none';
    document.getElementById('step2').style.display='block';
    document.getElementById('msg').innerHTML='<div class="msg ok">Код отправлен в Telegram!</div>';
  } else {
    document.getElementById('msg').innerHTML='<div class="msg err">Ошибка: '+d.error+'</div>';
  }
}
async function submitCode(){
  const code=document.getElementById('code').value;
  document.getElementById('msg').innerHTML='<div class="msg ok">Проверяю...</div>';
  const r=await fetch('/submit_code',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code})});
  const d=await r.json();
  if(d.ok){
    document.getElementById('step2').style.display='none';
    document.getElementById('step3').style.display='block';
    document.getElementById('session').textContent=d.session;
    document.getElementById('msg').innerHTML='';
  } else {
    document.getElementById('msg').innerHTML='<div class="msg err">Ошибка: '+d.error+'</div>';
  }
}
function copySession(){
  navigator.clipboard.writeText(document.getElementById('session').textContent);
  document.getElementById('msg').innerHTML='<div class="msg ok">Скопировано!</div>';
}
</script></body></html>"""

client = None
phone_hash = None

async def handle_index(request):
    return web.Response(text=HTML, content_type='text/html')

async def handle_request_code(request):
    global client, phone_hash
    try:
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        result = await client.send_code_request(PHONE)
        phone_hash = result.phone_code_hash
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})

async def handle_submit_code(request):
    global client, phone_hash
    data = await request.json()
    code = data.get("code", "").strip()
    try:
        await client.sign_in(PHONE, code, phone_code_hash=phone_hash)
        session = client.session.save()
        await client.disconnect()
        return web.json_response({"ok": True, "session": session})
    except Exception as e:
        return web.json_response({"ok": False, "error": str(e)})

app = web.Application()
app.router.add_get('/', handle_index)
app.router.add_post('/request_code', handle_request_code)
app.router.add_post('/submit_code', handle_submit_code)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    print(f"Auth server running on port {port}")
    web.run_app(app, host='0.0.0.0', port=port)
