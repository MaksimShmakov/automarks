"""Генерация JS-скрипта лендинга из строки воронки + глобальных констант.

Порт из el-tiktok-funnels-auto/backend/app/landing_templates.py (без изменений
логики). Два шаблона: A — лендинг с кнопкой, B — зеркало (autoredirect).
Плейсхолдеры вида __NAME__ подставляются простым replace (в JS полно фигурных
скобок, поэтому не format/jinja). Разработчик копирует готовый вывод дословно.
"""

from urllib.parse import quote

# --- Шаблон A: лендинг с кнопкой ---------------------------------------------
BUTTON_TEMPLATE = r"""<!-- Метрика: вставить перед основным скриптом -->
<script>
  var YM_COUNTER_ID = __YM_COUNTER_ID__; // счётчик Метрики
</script>
<!-- Основной скрипт воронки (лендинг с кнопкой) -->
<script>
(function () {
  var OFFER        = "__OFFER__";
  var BOT_URL      = "__BOT_URL__";
  var BOT_NAME     = "__BOT_NAME__";
  var WEBHOOK_URL  = "__WEBHOOK_URL__";
  var WEBHOOK_TOKEN= "__WEBHOOK_TOKEN__";
  var SS_KEY       = "form_click_id";
  var ID_LEN       = 10;
  function getCookie(n){ var m=document.cookie.match('(?:^|;)\\s*'+n+'=([^;]*)'); return m?decodeURIComponent(m[1]):''; }
  function getParam(n){ var m=new RegExp('[?&]'+n+'=([^&]+)').exec(location.search); return m?decodeURIComponent(m[1]):''; }
  function smartDecode(v){ if(!v)return v; var o=v; for(var i=0;i<3&&/%[0-9A-Fa-f]{2}/.test(o);i++){try{var d=decodeURIComponent(o); if(d===o)break; o=d;}catch(e){break;}} return o; }
  function getParamDecoded(n){ return smartDecode(getParam(n)); }
  function digitsOnly(v){ return String(v||'').replace(/\D/g,''); }
  function generateId(){
    var c='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789',o='';
    if(window.crypto&&crypto.getRandomValues){var b=new Uint8Array(ID_LEN);crypto.getRandomValues(b);for(var i=0;i<ID_LEN;i++)o+=c[b[i]%62];}
    else{for(var j=0;j<ID_LEN;j++)o+=c[Math.floor(Math.random()*62)];}
    return o;
  }
  function getFormClickId(){
    var id=''; try{id=sessionStorage.getItem(SS_KEY)||'';}catch(e){}
    if(id&&id.length!==ID_LEN)id='';
    if(!id){id=generateId(); try{sessionStorage.setItem(SS_KEY,id);}catch(e){}}
    return id;
  }
  var formClickId=getFormClickId(), paramsSent=false;
  function sendParamsToMetrika(){
    if(paramsSent)return true;
    if(typeof window.ym==='function'&&typeof YM_COUNTER_ID!=='undefined'&&YM_COUNTER_ID){
      window.ym(YM_COUNTER_ID,'params',{form_click_id:formClickId}); paramsSent=true; return true;
    }
    return false;
  }
  (function poll(a){ if(sendParamsToMetrika())return; if(a>=30)return; setTimeout(function(){poll(a+1);}, 500); })(0);
  function sendToWebhook(p){
    try{fetch(WEBHOOK_URL,{method:'POST',headers:{'Content-Type':'application/json','X-WebhookToken':WEBHOOK_TOKEN},body:JSON.stringify(p),keepalive:true}).catch(function(e){console.warn(e);});}catch(e){}
  }
  function handleClick(e){
    var a=e.target&&e.target.closest&&e.target.closest('a[href*="'+BOT_NAME+'"]');
    if(!a)return; e.preventDefault();
    var startId=generateId();
    var clientId=digitsOnly(getCookie('_ym_uid'));
    var yclid=digitsOnly(getParam('yclid'));
    var ttp=getCookie('_ttp')||null;
    var ttclid=getParam('ttclid')||getCookie('ttclid')||null;
    sendParamsToMetrika();
    if(typeof ttq!=='undefined'){try{ttq.track('ClickButton',{},{event_id:'click-'+startId});}catch(e){}}
    sendToWebhook({
      token:WEBHOOK_TOKEN, startID:startId, formClickID:formClickId,
      clientID:clientId||null, yclid:yclid||null, tiktok_ttp:ttp, tiktok_ttclid:ttclid,
      gateway:OFFER, landing:location.pathname||null,
      utm_source:getParam('utm_source')||null, utm_medium:getParam('utm_medium')||null,
      utm_campaign:getParamDecoded('utm_campaign')||null, utm_content:getParamDecoded('utm_content')||null,
      utm_term:getParamDecoded('utm_term')||null, utm_id:getParam('utm_id')||null,
      ad_id:getParam('adid')||getParam('ad_id')||null,
      tiktok_pixel_code: '__PIXEL_CODE__'
    });
    var start=[OFFER,clientId||'0',startId,formClickId].join('_');
    if(start.length>64)start=start.slice(0,64);
    window.location.href=BOT_URL+'?start='+start;
  }
  document.addEventListener('click',handleClick,true);
})();
</script>
"""

# --- Шаблон B: зеркало (autoredirect) ----------------------------------------
MIRROR_TEMPLATE = r"""<!-- Метрика: желательна, но не обязательна для зеркала -->
<script>
  var YM_COUNTER_ID = __YM_COUNTER_ID__; // счётчик Метрики
</script>
<!-- Основной скрипт воронки (зеркало) -->
<script>
(function () {
  var OFFER        = "__OFFER__";
  var BOT_URL      = "__BOT_URL__";
  var WEBHOOK_URL  = "__WEBHOOK_URL__";
  var WEBHOOK_TOKEN= "__WEBHOOK_TOKEN__";
  var SS_KEY       = "form_click_id";
  var ID_LEN       = 10;
  var MAX_WAIT_MS  = 4000;
  function getCookie(n){ var m=document.cookie.match('(?:^|;)\\s*'+n+'=([^;]*)'); return m?decodeURIComponent(m[1]):''; }
  function getParam(n){ var m=new RegExp('[?&]'+n+'=([^&]+)').exec(location.search); return m?decodeURIComponent(m[1]):''; }
  function smartDecode(v){ if(!v)return v; var o=v; for(var i=0;i<3&&/%[0-9A-Fa-f]{2}/.test(o);i++){try{var d=decodeURIComponent(o); if(d===o)break; o=d;}catch(e){break;}} return o; }
  function getParamDecoded(n){ return smartDecode(getParam(n)); }
  function digitsOnly(v){ return String(v||'').replace(/\D/g,''); }
  function generateId(){
    var c='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789',o='';
    if(window.crypto&&crypto.getRandomValues){var b=new Uint8Array(ID_LEN);crypto.getRandomValues(b);for(var i=0;i<ID_LEN;i++)o+=c[b[i]%62];}
    else{for(var j=0;j<ID_LEN;j++)o+=c[Math.floor(Math.random()*62)];}
    return o;
  }
  function getFormClickId(){
    var id=''; try{id=sessionStorage.getItem(SS_KEY)||'';}catch(e){}
    if(id&&id.length!==ID_LEN)id='';
    if(!id){id=generateId(); try{sessionStorage.setItem(SS_KEY,id);}catch(e){}}
    return id;
  }
  var formClickId=getFormClickId(), startId=generateId(), paramsSent=false;
  function sendParamsToMetrika(){
    if(paramsSent)return true;
    if(typeof window.ym==='function'&&typeof YM_COUNTER_ID!=='undefined'&&YM_COUNTER_ID){
      window.ym(YM_COUNTER_ID,'params',{form_click_id:formClickId}); paramsSent=true; return true;
    }
    return false;
  }
  function sendToWebhook(p){
    try{fetch(WEBHOOK_URL,{method:'POST',headers:{'Content-Type':'application/json','X-WebhookToken':WEBHOOK_TOKEN},body:JSON.stringify(p),keepalive:true}).catch(function(e){console.warn(e);});}catch(e){}
  }
  var redirected=false;
  function go(){
    if(redirected)return; redirected=true;
    if(typeof ttq!=='undefined'){try{ttq.track('ClickButton',{},{event_id:'click-'+startId});}catch(e){}}
    var clientId=digitsOnly(getCookie('_ym_uid'));
    var yclid=digitsOnly(getParam('yclid'));
    var ttp=getCookie('_ttp')||null;
    var ttclid=getParam('ttclid')||getCookie('ttclid')||null;
    sendToWebhook({
      token:WEBHOOK_TOKEN, startID:startId, formClickID:formClickId,
      clientID:clientId||null, yclid:yclid||null, tiktok_ttp:ttp, tiktok_ttclid:ttclid,
      gateway:OFFER, landing:location.pathname||null,
      utm_source:getParam('utm_source')||null, utm_medium:getParam('utm_medium')||null,
      utm_campaign:getParamDecoded('utm_campaign')||null, utm_content:getParamDecoded('utm_content')||null,
      utm_term:getParamDecoded('utm_term')||null, utm_id:getParam('utm_id')||null,
      ad_id:getParam('adid')||getParam('ad_id')||null,
      tiktok_pixel_code: '__PIXEL_CODE__'
    });
    var start=[OFFER,clientId||'0',startId,formClickId].join('_');
    if(start.length>64)start=start.slice(0,64);
    setTimeout(function(){ window.location.href=BOT_URL+'?start='+start; },300);
  }
  document.addEventListener("DOMContentLoaded",function(){
    (function poll(el){ if(sendParamsToMetrika()){setTimeout(go,500);return;} if(el>=MAX_WAIT_MS){go();return;} setTimeout(function(){poll(el+250);},250); })(0);
  });
})();
</script>
"""


def render_utm_link(*, base_url, landing_endpoint, utm_source, utm_medium, utm_term):
    """Собрать рекламную ссылку. source/medium/term — из воронки; campaign/content/id
    и ttclid — фиксированные макросы TikTok (подставляются им при клике)."""

    def enc(v):
        return quote(v or "", safe="")

    return (
        f"{base_url.rstrip('/')}{landing_endpoint}"
        f"?utm_source={enc(utm_source)}"
        f"&utm_medium={enc(utm_medium)}"
        f"&utm_campaign=__CAMPAIGN_NAME__"
        f"&utm_content=__CID__"
        f"&utm_term={enc(utm_term)}"
        f"&utm_id=__CAMPAIGN_ID__"
        f"&ttclid=__CLICKID__"
    )


def render_landing_script(
    *,
    page_type,
    offer,
    bot_url,
    bot_name,
    pixel_code,
    ym_counter_id,
    webhook_url,
    webhook_token,
):
    tpl = BUTTON_TEMPLATE if page_type == "button" else MIRROR_TEMPLATE
    return (
        tpl.replace("__YM_COUNTER_ID__", str(ym_counter_id))
        .replace("__OFFER__", offer or "")
        .replace("__BOT_URL__", bot_url or "")
        .replace("__BOT_NAME__", bot_name or "")
        .replace("__WEBHOOK_URL__", webhook_url or "")
        .replace("__WEBHOOK_TOKEN__", webhook_token or "")
        .replace("__PIXEL_CODE__", pixel_code or "")
    )
