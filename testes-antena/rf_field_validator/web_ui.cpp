#include "web_ui.h"
#include "config.h"
#include "state_machine.h"
#include "csv_log.h"
#include "supervision.h"
#include "weblog.h"
#include <WebServer.h>
#include <LittleFS.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include <time.h>

// ── Estado global ─────────────────────────────────────────────
bool g_epoch_anchored  = false;
static bool _web_started = false;   // garante que web_ui_init só roda uma vez

// ── Servidor HTTP na porta 80 ─────────────────────────────────
static WebServer _srv(WEB_UI_PORT);

// ── Página HTML completa (servida do flash) ───────────────────
static const char _PAGE[] PROGMEM = R"HTML(
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>RF Validator</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:monospace;background:#0d1117;color:#c9d1d9;padding:10px;max-width:520px;margin:auto}
.hd{display:flex;justify-content:space-between;align-items:center;padding:8px 12px;background:#161b22;border-radius:6px;margin-bottom:8px}
.htitle{color:#58a6ff;font-size:.92em;font-weight:bold}
#sb{padding:4px 10px;border-radius:4px;font-weight:bold;font-size:.82em}
#tbar{display:none;text-align:center;padding:7px 12px;background:#0d2a0d;border:1px solid #238636;border-radius:6px;margin-bottom:8px;font-size:1.1em;color:#3fb950;letter-spacing:.06em}
.panel{background:#161b22;border:1px solid #30363d;border-radius:6px;margin-bottom:8px;overflow:hidden}
.ph{padding:9px 12px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;user-select:none;-webkit-user-select:none}
.ph h3{color:#8b949e;font-size:.76em;text-transform:uppercase;letter-spacing:.08em;margin:0}
.ph:after{content:'\25B2';font-size:.6em;color:#484f58}
.panel.col .ph:after{content:'\25BC'}
.panel.col .pc{display:none}
.pc{padding:10px 12px}
.sr{display:flex;justify-content:space-between;align-items:center;padding:3px 0;border-bottom:1px solid #21262d;font-size:.85em}
.sr:last-child{border-bottom:none}
.sl{color:#8b949e}
.sv{color:#e6edf3;font-weight:bold}
.bw{height:5px;background:#21262d;border-radius:3px;margin:2px 0 6px}
.bf{height:5px;border-radius:3px;transition:width .5s,background .5s;width:0%}
.si{background:#1c1c1c;color:#8b949e}
.sr2{background:#1b2a49;color:#58a6ff}
.sg{background:#1a4731;color:#3fb950}
.sy{background:#2d2016;color:#d29922}
button{background:#21262d;color:#c9d1d9;border:1px solid #30363d;border-radius:4px;padding:7px 10px;cursor:pointer;font-family:monospace;font-size:.82em;width:100%}
button:hover{background:#30363d}
.bs{background:#1a4731;color:#3fb950;border-color:#238636}
.bs:hover{background:#238636}
.bx{background:#3d1616;color:#f85149;border-color:#6e2020}
.bx:hover{background:#6e2020}
.bx-arm{background:#6e2020;color:#fff;border-color:#da3633;animation:pulse .4s infinite alternate}
.bp{background:#1b2a49;color:#58a6ff;border-color:#1f6feb;font-size:.78em;padding:5px 8px;width:auto}
.bp:hover{background:#1f6feb;color:#fff}
@keyframes pulse{from{opacity:1}to{opacity:.7}}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:6px}
.g3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-bottom:6px}
label span{font-size:.75em;color:#8b949e;display:block;margin-bottom:2px}
input[type=text]{background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:4px;padding:5px 7px;width:100%;font-family:monospace;font-size:.85em}
input[type=text]:focus{outline:none;border-color:#58a6ff}
.msg{padding:5px 9px;border-radius:4px;margin-top:6px;font-size:.81em;display:none}
.mo{background:#1a4731;color:#3fb950}
.me{background:#3d1616;color:#f85149}
.mw{background:#2d2016;color:#d29922}
.term{background:#010409;border:1px solid #21262d;border-radius:4px;padding:8px;height:200px;overflow-y:auto;font-size:.74em;line-height:1.6;word-break:break-all}
.wb{display:none;padding:6px 10px;background:#2d2016;border:1px solid #d29922;border-radius:4px;color:#d29922;font-size:.82em;margin-bottom:8px}
.li{display:flex;justify-content:space-between;align-items:center;padding:5px 2px;border-bottom:1px solid #21262d;font-size:.82em}
.li:last-child{border:none}
.la{display:flex;gap:10px;align-items:center}
a{color:#58a6ff;text-decoration:none}
a:hover{text-decoration:underline}
a.del{color:#f85149}
#spark{width:100%;height:80px;display:block;background:#010409;border-radius:4px}
</style>
</head>
<body>

<div class="hd">
  <span class="htitle">&#x1F4F6; RF Field Validator N3.0</span>
  <span id="sb" class="si">IDLE</span>
</div>
<div id="tbar">
  <span id="timer">00:00</span>
  <span id="blkd" style="display:none;color:#d29922;font-size:.8em;margin-left:10px">
    &#x25A0; Bloco <span id="blkn">1</span>/3
  </span>
</div>
<div id="wb" class="wb">&#x26A0; FLUSH_INCOMPLETE &#x2014; dados podem estar faltando no CSV</div>
<div id="desc" style="font-size:.81em;text-align:center;padding:4px 8px;margin-bottom:6px;min-height:1.3em;color:#8b949e"></div>

<div class="panel" id="p-st">
  <div class="ph" onclick="tp('p-st')"><h3>Status</h3></div>
  <div class="pc">
    <div class="sr"><span class="sl">Arquivo</span><span class="sv" id="fname" style="font-size:.77em">-</span></div>
    <div class="sr"><span class="sl">Config</span><span class="sv" id="cfg">-</span></div>
    <div class="sr"><span class="sl">RSSI</span><span class="sv" id="rssi-v">--- dBm</span></div>
    <div class="bw"><div class="bf" id="rssi-b"></div></div>
    <div class="sr"><span class="sl">V_IN</span><span class="sv" id="vin-v">---</span></div>
    <div class="bw"><div class="bf" id="vin-b"></div></div>
    <div class="sr"><span class="sl">Temp</span><span class="sv" id="temp-v">--</span></div>
    <div class="sr"><span class="sl">Amostras</span><span class="sv" id="samp">0</span></div>
    <div class="sr"><span class="sl">Ring pendente</span><span class="sv" id="ring">0</span></div>
    <div class="sr"><span class="sl">Flash livre</span><span class="sv" id="fl">---</span></div>
    <div class="sr"><span class="sl">NTP</span><span class="sv" id="ntp">---</span></div>
  </div>
</div>

<div class="panel" id="p-rs">
  <div class="ph" onclick="tp('p-rs')"><h3>RSSI ao vivo &#x2014; &#xFA;ltimos 60 ciclos</h3></div>
  <div class="pc" style="padding-bottom:8px">
    <canvas id="spark" width="460" height="80"></canvas>
    <div style="display:flex;justify-content:space-between;margin-top:4px;font-size:.7em;color:#484f58">
      <span>&#x2015; <span style="color:rgba(210,153,34,.7)">-65 dBm (limite campo)</span></span>
      <span>&#x2015; <span style="color:rgba(248,81,73,.6)">-75 dBm (cr&#xED;tico)</span></span>
    </div>
  </div>
</div>

<div class="panel col" id="p-ds">
  <div class="ph" onclick="tp('p-ds')"><h3>Dist&#xE2;ncia estimada</h3></div>
  <div class="pc">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
      <span id="dv" style="font-size:1.6em;font-weight:bold;color:#8b949e">&#x2014;</span>
      <button class="bp" onclick="calRef()">Calibrar a 1 m</button>
    </div>
    <div id="dw" style="font-size:.75em;color:#d29922;margin-bottom:6px">
      &#x26A0; Fique a 1 m do celular e pressione Calibrar para ativar
    </div>
    <div class="bw" style="height:7px"><div class="bf" id="db" style="height:7px;width:0%"></div></div>
    <div style="display:flex;justify-content:space-between;font-size:.67em;color:#484f58;margin-top:2px">
      <span>0</span><span>5 m</span><span>10 m</span><span>15 m</span><span>20 m</span>
    </div>
    <label style="margin-top:8px;display:flex;align-items:center;gap:6px;font-size:.8em;color:#8b949e">
      <input type="checkbox" id="amtog"> Auto-mark 3/5/10/15 m durante CLOCK
    </label>
    <div id="dm" class="msg"></div>
  </div>
</div>

<div class="panel" id="p-cf">
  <div class="ph" onclick="tp('p-cf')"><h3>Configurar</h3></div>
  <div class="pc">
    <div class="g3">
      <label><span>Antena</span><input type="text" id="ant" value="A5.1" maxlength="5" list="dl-ant">
        <datalist id="dl-ant"><option value="A4.1"><option value="A4.2"><option value="A5.1"><option value="A5.2"><option value="A5.3"><option value="INT"></datalist>
      </label>
      <label><span>Local</span><input type="text" id="loc" value="MESA" maxlength="7" list="dl-loc">
        <datalist id="dl-loc"><option value="MESA"><option value="TETO"><option value="CAMPO"><option value="CAB"><option value="GUARITA"><option value="PATIO"><option value="GALPAO"><option value="MOTOR"><option value="PAINEL"><option value="SOLO"><option value="EXT"></datalist>
      </label>
      <label><span>Cond.</span><input type="text" id="cnd" value="DES" maxlength="4" list="dl-cnd">
        <datalist id="dl-cnd"><option value="DES"><option value="LIG"><option value="RUN"><option value="VIB"><option value="EMI"></datalist>
      </label>
    </div>
    <label style="margin-top:6px;display:block"><span>Alvo TCP (notebook)</span>
      <input type="text" id="tcp" value="" maxlength="40" placeholder="192.168.x.x">
    </label>
    <button onclick="sendCfg()" style="margin-top:8px">Aplicar CONFIG</button>
    <div id="cm" class="msg"></div>
  </div>
</div>

<div class="panel" id="p-ct">
  <div class="ph" onclick="tp('p-ct')"><h3>Controle</h3></div>
  <div class="pc">
    <div class="g3">
      <button class="bs" onclick="cmd('start_walk')">WALK</button>
      <button class="bs" onclick="cmd('start_walk_cold')">WALK cold</button>
      <button class="bs" onclick="cmd('start_clock')">CLOCK</button>
    </div>
    <div class="g2">
      <button class="bs" onclick="cmd('start_burn')">BURN</button>
      <button class="bs" onclick="cmd('start_burn3')">BURN 3&#xD7;60</button>
    </div>
    <button id="btn-stop" class="bx" onclick="armStop()">&#x23F9; STOP</button>
    <div id="rm" class="msg"></div>
  </div>
</div>

<div class="panel col" id="p-mk">
  <div class="ph" onclick="tp('p-mk')"><h3>Marcar &#x2014; CLOCK</h3></div>
  <div class="pc">
    <div style="display:flex;flex-wrap:wrap;gap:5px;margin-bottom:8px">
      <button class="bp" onclick="qmark('3M')">3 m</button>
      <button class="bp" onclick="qmark('5M')">5 m</button>
      <button class="bp" onclick="qmark('10M')">10 m</button>
      <button class="bp" onclick="qmark('15M')">15 m</button>
      <button class="bp" onclick="qmark('CABINE')">Cabine</button>
      <button class="bp" onclick="qmark('MOTOR')">Motor</button>
      <button class="bp" onclick="qmark('FRENTE')">Frente</button>
      <button class="bp" onclick="qmark('TRAS')">Trás</button>
    </div>
    <div style="display:flex;gap:6px">
      <input type="text" id="mlbl" value="P1" maxlength="8" style="flex:1">
      <button style="width:auto;padding:7px 14px" onclick="sendMark()">Marcar</button>
    </div>
    <div id="mm" class="msg"></div>
  </div>
</div>

<div class="panel" id="p-tm">
  <div class="ph" onclick="tp('p-tm')"><h3>Terminal do sistema</h3></div>
  <div class="pc">
    <div id="term" class="term" aria-live="polite">
      <span style="color:#484f58">Aguardando...</span>
    </div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-top:6px">
      <label style="font-size:.75em;color:#8b949e;display:flex;align-items:center;gap:4px">
        <input type="checkbox" id="ta" checked> auto-scroll
      </label>
      <button style="width:auto;padding:4px 10px;font-size:.76em" onclick="clrTerm()">Limpar</button>
    </div>
  </div>
</div>


<div class="panel col" id="p-lg">
  <div class="ph" onclick="tp('p-lg')"><h3>Logs</h3></div>
  <div class="pc">
    <div class="g2" style="margin-bottom:8px">
      <button onclick="loadLogs()">&#x21BB; Atualizar lista</button>
      <button id="btn-dl" onclick="dlAll()">&#x2B07; Baixar todos</button>
    </div>
    <div id="ll"><em style="color:#8b949e;font-size:.82em">Clique em Atualizar lista.</em></div>
  </div>
</div>

<script>
var SC={IDLE:'si',READY:'sr2',RUNNING_WALK:'sg',RUNNING_CLOCK:'sg',
        RUNNING_BURN:'sg',RUNNING_BURN3:'sg',FLUSHING:'sy'};

// ── Collapsible panels ────────────────────────────────────────
function tp(id){
  var p=document.getElementById(id);
  p.classList.toggle('col');
  if(id==='p-rs'&&!p.classList.contains('col'))setTimeout(function(){rsz();dsp();},30);
  var o={};
  document.querySelectorAll('.panel').forEach(function(q){if(q.id)o[q.id]=q.classList.contains('col');});
  try{localStorage.setItem('rfv',JSON.stringify(o));}catch(e){}
}
(function(){
  try{
    var o=JSON.parse(localStorage.getItem('rfv')||'{}');
    document.querySelectorAll('.panel').forEach(function(p){
      if(p.id&&o[p.id]===true)p.classList.add('col');
      else if(p.id&&o[p.id]===false)p.classList.remove('col');
    });
  }catch(e){}
})();

// ── Timer ─────────────────────────────────────────────────────
var _tb=0,_tr=0,_ti=null;
function fmt(ms){var s=Math.floor(ms/1000),m=Math.floor(s/60);s=s%60;return(m<10?'0':'')+m+':'+(s<10?'0':'')+s;}
function startT(e){
  _tb=e;_tr=Date.now();
  document.getElementById('tbar').style.display='block';
  if(_ti)clearInterval(_ti);
  _ti=setInterval(function(){document.getElementById('timer').textContent=fmt(_tb+(Date.now()-_tr));},500);
}
function stopT(){
  if(_ti){clearInterval(_ti);_ti=null;}
  document.getElementById('tbar').style.display='none';
  document.getElementById('timer').textContent='00:00';
}

// ── Messages ─────────────────────────────────────────────────
function msg(id,ok,t,w){
  var e=document.getElementById(id);
  e.className='msg '+(w?'mw':ok?'mo':'me');
  e.textContent=t;e.style.display='block';
  setTimeout(function(){e.style.display='none';},3500);
}

// ── Fetch helpers ─────────────────────────────────────────────
function post(b,cb){
  fetch('/cmd',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:b})
  .then(function(r){return r.json();}).then(cb)
  .catch(function(){cb({ok:false,msg:'Erro de rede'});});
}
function cmd(a){post('action='+a,function(r){msg('rm',r.ok,r.msg);});}
function qmark(l){document.getElementById('mlbl').value=l;sendMark();}

// ── STOP 2-tap ────────────────────────────────────────────────
var _sa2=false,_st2=null;
function armStop(){
  var b=document.getElementById('btn-stop');
  if(!_sa2){
    _sa2=true;b.textContent='Confirmar STOP?';b.className='bx bx-arm';
    _st2=setTimeout(function(){_sa2=false;b.textContent='\u23F9 STOP';b.className='bx';},3000);
  }else{
    clearTimeout(_st2);_sa2=false;b.textContent='\u23F9 STOP';b.className='bx';
    post('action=stop',function(r){msg('rm',r.ok,r.msg);});
  }
}

// ── Config / Mark ─────────────────────────────────────────────
function sendCfg(){
  var a=document.getElementById('ant').value.trim();
  var l=document.getElementById('loc').value.trim();
  var c=document.getElementById('cnd').value.trim();
  var t=document.getElementById('tcp').value.trim();
  post('action=config&ant='+encodeURIComponent(a)+'&loc='+encodeURIComponent(l)
    +'&cnd='+encodeURIComponent(c)+'&tcp='+encodeURIComponent(t),
    function(r){msg('cm',r.ok,r.msg);});
}
function sendMark(){
  var m=document.getElementById('mlbl').value.trim();
  post('action=mark&label='+encodeURIComponent(m),function(r){msg('mm',r.ok,r.msg);});
}

// ── RSSI Sparkline ────────────────────────────────────────────
var _rh=[];
var _cv=document.getElementById('spark');
var _cx=_cv?_cv.getContext('2d'):null;
function rsz(){if(!_cv)return;_cv.width=_cv.offsetWidth||460;_cv.height=80;}
window.addEventListener('resize',function(){rsz();dsp();});
rsz();

function dsp(){
  if(!_cx||!_cv||_rh.length<2)return;
  var w=_cv.width,h=_cv.height,n=_rh.length;
  _cx.clearRect(0,0,w,h);
  var lo=-100,hi=-40;
  function fy(v){return h-Math.max(0,Math.min(h,(v-lo)/(hi-lo)*h));}
  _cx.save();_cx.setLineDash([3,4]);_cx.lineWidth=1;
  _cx.strokeStyle='rgba(210,153,34,.45)';
  _cx.beginPath();_cx.moveTo(0,fy(-65));_cx.lineTo(w,fy(-65));_cx.stroke();
  _cx.strokeStyle='rgba(248,81,73,.35)';
  _cx.beginPath();_cx.moveTo(0,fy(-75));_cx.lineTo(w,fy(-75));_cx.stroke();
  _cx.restore();
  var lv=_rh[n-1];
  var col=lv>=-65?'#3fb950':lv>=-75?'#d29922':'#f85149';
  _cx.beginPath();
  for(var i=0;i<n;i++){var x=i/(n-1)*w,y=fy(_rh[i]);if(i===0)_cx.moveTo(x,y);else _cx.lineTo(x,y);}
  _cx.lineTo(w,h);_cx.lineTo(0,h);_cx.closePath();
  _cx.fillStyle=col+'1a';_cx.fill();
  _cx.beginPath();
  for(var j=0;j<n;j++){var x=j/(n-1)*w,y=fy(_rh[j]);if(j===0)_cx.moveTo(x,y);else _cx.lineTo(x,y);}
  _cx.strokeStyle=col;_cx.lineWidth=1.5;_cx.setLineDash([]);_cx.stroke();
}

// ── Distância estimada (log-distance path-loss model) ─────────
// d = 10^((RSSI_ref - RSSI) / (10 * n)),  n=2.5 outdoor Wi-Fi
var _r1m=parseFloat(localStorage.getItem('rfv_r1m')||'NaN');
var _PLN=2.5;
var _amkd={};              // limiares já marcados nesta sessão CLOCK
var _THRS=[3,5,10,15];     // metros para auto-mark
var _TLBL=['3M','5M','10M','15M'];
var _HYST=1.5;             // histerese (m) para resetar um limiar
var _cst='IDLE';           // estado atual (atualizado por updSt)

function _avgRssi(){
  if(!_rh.length)return -127;
  var n=Math.min(5,_rh.length),s=0;
  for(var i=_rh.length-n;i<_rh.length;i++)s+=_rh[i];
  return s/n;
}

function calRef(){
  var r=_avgRssi();
  if(r<=-127){msg('dm',false,'Sem RSSI — aguarde Wi-Fi');return;}
  _r1m=Math.round(r);
  localStorage.setItem('rfv_r1m',String(_r1m));
  document.getElementById('dw').style.display='none';
  msg('dm',true,'Ref 1 m = '+_r1m+' dBm — pode abrir o painel e afastar');
  updDist();
}

function updDist(){
  var dv=document.getElementById('dv');
  var db=document.getElementById('db');
  var dw=document.getElementById('dw');
  if(!dv)return;
  if(isNaN(_r1m)){
    dv.textContent='—';dv.style.color='#8b949e';
    if(dw)dw.style.display='block';
    return;
  }
  if(dw)dw.style.display='none';
  var r=_avgRssi();
  if(r<=-127){dv.textContent='—';dv.style.color='#8b949e';return;}
  var d=Math.pow(10,(_r1m-r)/(10*_PLN));
  var col=d<4?'#3fb950':d<8?'#d29922':'#58a6ff';
  dv.textContent='~'+d.toFixed(1)+' m';
  dv.style.color=col;
  db.style.width=Math.min(100,d/20*100)+'%';
  db.style.background=col;
  // Auto-mark: envia MARK ao cruzar cada limiar durante CLOCK
  var amEl=document.getElementById('amtog');
  if(amEl&&amEl.checked&&_cst==='RUNNING_CLOCK'){
    _THRS.forEach(function(t,i){
      if(!_amkd[t]&&d>=t){
        _amkd[t]=true;
        post('action=mark&label='+_TLBL[i],function(r2){msg('dm',r2.ok,'Auto-mark: '+_TLBL[i]);});
      }
      if(_amkd[t]&&d<t-_HYST)_amkd[t]=false;
    });
  }else if(_cst!=='RUNNING_CLOCK'){
    _amkd={};
  }
}

// ── Status ────────────────────────────────────────────────────
var _wr=false;
function updSt(){
  fetch('/status').then(function(r){return r.json();}).then(function(d){
    _cst=d.state;
    var sb=document.getElementById('sb');
    sb.textContent=d.state;sb.className=SC[d.state]||'si';
    var run=d.elapsed_ms>0;
    if(run)startT(d.elapsed_ms);else if(_wr)stopT();
    _wr=run;
    var bd=document.getElementById('blkd');
    if(d.state==='RUNNING_BURN3'){
      bd.style.display='inline';document.getElementById('blkn').textContent=d.block||1;
    }else bd.style.display='none';
    document.getElementById('wb').style.display=d.flush_warn?'block':'none';
    document.getElementById('cfg').textContent=d.cfg;
    document.getElementById('fname').textContent=d.fname||'-';
    var tf=document.getElementById('tcp');if(tf&&!tf.matches(':focus'))tf.value=d.tcp_host||'';
    var rv=d.rssi;
    document.getElementById('rssi-v').textContent=rv+' dBm';
    var rc=rv>=-65?'#3fb950':rv>=-75?'#d29922':'#f85149';
    var rp=Math.max(0,Math.min(100,(rv+100)/60*100));
    document.getElementById('rssi-b').style.width=rp+'%';
    document.getElementById('rssi-b').style.background=rc;
    if(rv!==-127){_rh.push(rv);if(_rh.length>60)_rh.shift();dsp();}
    updDist();
    document.getElementById('temp-v').textContent=d.temp_c!=null?d.temp_c.toFixed(1)+'\u00b0C':'--';
    document.getElementById('samp').textContent=d.samples;
    document.getElementById('ring').textContent=d.ring+' linhas';
    var ve=document.getElementById('vin-v');
    if(d.vin_mv>0){
      var vc=d.vin_mv>=11000?'#3fb950':d.vin_mv>=10500?'#d29922':'#f85149';
      ve.textContent=(d.vin_mv/1000).toFixed(2)+' V';ve.style.color=vc;
      var vp=Math.max(0,Math.min(100,(d.vin_mv-9000)/5000*100));
      document.getElementById('vin-b').style.width=vp+'%';
      document.getElementById('vin-b').style.background=vc;
    }else{ve.textContent='sem sensor';ve.style.color='#8b949e';}
    var fe=document.getElementById('fl');
    fe.textContent=d.flash_kb+' KB';fe.style.color=d.flash_warn?'#f85149':'#e6edf3';
    document.getElementById('ntp').textContent=d.ntp?'ancorado':'nao ancorado';
    // Descrição humanizada
    var de=document.getElementById('desc'),dc,dt;
    if(d.state==='IDLE'){
      dc='#8b949e';dt='Aguardando conexão Wi-Fi...';
    }else if(d.state==='READY'){
      var hasConfig=(d.cfg&&d.cfg!=='-/-/-'&&d.cfg!=='//');
      dc=hasConfig?'#3fb950':'#d29922';
      dt=hasConfig?'Pronto para iniciar — '+d.cfg:'Configure antena, local e condição antes de iniciar';
    }else if(d.state==='RUNNING_WALK'){
      dc='#58a6ff';dt='Coletando RSSI contínuo a 2 Hz — mova-se pelo ambiente';
    }else if(d.state==='RUNNING_CLOCK'){
      dc='#58a6ff';dt='Mapeando RSSI por posição — marque distâncias/locais ou use auto-mark';
    }else if(d.state==='RUNNING_BURN'){
      dc='#58a6ff';dt='Medindo throughput TCP + PLR — tcp_sink.py deve estar ativo no notebook';
    }else if(d.state==='RUNNING_BURN3'){
      dc='#58a6ff';dt='BURN 3\u00d760s — bloco '+(d.block||1)+'/3 — tcp_sink.py deve estar ativo no notebook';
    }else if(d.state==='FLUSHING'){
      dc='#d29922';dt='Encerrando — gravando dados no flash, aguarde...';
    }else{dc='#8b949e';dt='';}
    de.style.color=dc;de.textContent=dt;
  }).catch(function(){});
}

// ── Weblog: terminal ─────────────────────────────────────────
var _tn=0;
function _lc(s){
  if(s.indexOf('[ERR]')>=0||s.indexOf('[FATAL]')>=0||s.indexOf('BROWNOUT')>=0)return'#f85149';
  if(s.indexOf('[WARN]')>=0||s.indexOf('INCOMPLETE')>=0||s.indexOf('LINK_DOWN')>=0)return'#d29922';
  if(s.indexOf('[OK]')>=0||s.indexOf('LINK_UP')>=0)return'#3fb950';
  if(s.indexOf('[BTN]')>=0||s.indexOf('[NTP]')>=0||s.indexOf('[Web]')>=0)return'#58a6ff';
  return'#c9d1d9';
}
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function clrTerm(){document.getElementById('term').innerHTML='<span style="color:#484f58">Limpo.</span>';}

function updLog(){
  fetch('/weblog').then(function(r){return r.json();}).then(function(d){
    if(!d||!d.lines||d.n===_tn)return;
    _tn=d.n;
    var te=document.getElementById('term'),h='';
    d.lines.forEach(function(l){h+='<div style="color:'+_lc(l)+'">'+esc(l)+'</div>';});
    te.innerHTML=h||'<span style="color:#484f58">Vazio.</span>';
    if(document.getElementById('ta').checked)te.scrollTop=te.scrollHeight;
  }).catch(function(){});
}

// ── Logs ─────────────────────────────────────────────────────
function loadLogs(){
  fetch('/logs').then(function(r){return r.json();}).then(function(d){
    var h='';
    if(d.files&&d.files.length){
      d.files.forEach(function(f){
        var kb=(f.size/1024).toFixed(1),en=encodeURIComponent(f.name);
        h+='<div class="li"><span>'+f.name+'<br><span style="color:#8b949e">'+kb+' KB</span></span>'
          +'<div class="la"><a href="/download?f='+en+'">baixar</a>'
          +'<a class="del" href="#" onclick="delF(\''+en+'\');return false;">apagar</a>'
          +'</div></div>';
      });
    }else h='<em style="color:#8b949e;font-size:.82em">Nenhum log.</em>';
    document.getElementById('ll').innerHTML=h;
  }).catch(function(){document.getElementById('ll').innerHTML='<em style="color:#f85149">Erro.</em>';});
}
function delF(en){
  if(!confirm('Apagar '+decodeURIComponent(en)+'?'))return;
  fetch('/delete?f='+en).then(function(r){return r.json();}).then(function(d){
    if(d.ok)loadLogs();else alert('Erro: '+d.msg);
  }).catch(function(){alert('Erro de rede');});
}

// ── ZIP ───────────────────────────────────────────────────────
var _ct=(function(){var t=[];for(var i=0;i<256;i++){var c=i;for(var j=0;j<8;j++)c=c&1?(0xEDB88320^(c>>>1)):c>>>1;t[i]=c>>>0;}return t;})();
function _c32(u){var c=0xFFFFFFFF;for(var i=0;i<u.length;i++)c=(_ct[(c^u[i])&0xFF]^(c>>>8))>>>0;return(c^0xFFFFFFFF)>>>0;}
function _zip(fs){
  function w4(v,b,o){b[o]=v&0xFF;b[o+1]=(v>>8)&0xFF;b[o+2]=(v>>16)&0xFF;b[o+3]=(v>>24)&0xFF;}
  function w2(v,b,o){b[o]=v&0xFF;b[o+1]=(v>>8)&0xFF;}
  var pts=[],cds=[],of=0,ec=new TextEncoder();
  fs.forEach(function(f){
    var nm=ec.encode(f.name),d=f.data,cr=_c32(d),sz=d.length;
    var lh=new Uint8Array(30+nm.length);
    w4(0x04034b50,lh,0);w2(20,lh,4);w2(0,lh,6);w2(0,lh,8);w2(0,lh,10);w2(0,lh,12);
    w4(cr,lh,14);w4(sz,lh,18);w4(sz,lh,22);w2(nm.length,lh,26);w2(0,lh,28);lh.set(nm,30);
    var cd=new Uint8Array(46+nm.length);
    w4(0x02014b50,cd,0);w2(20,cd,4);w2(20,cd,6);w2(0,cd,8);w2(0,cd,10);w2(0,cd,12);w2(0,cd,14);
    w4(cr,cd,16);w4(sz,cd,20);w4(sz,cd,24);w2(nm.length,cd,28);w2(0,cd,30);w2(0,cd,32);
    w2(0,cd,34);w2(0,cd,36);w4(0,cd,38);w4(of,cd,42);cd.set(nm,46);
    pts.push(lh,d);cds.push(cd);of+=lh.length+sz;
  });
  var co=of,cs=cds.reduce(function(a,c){return a+c.length;},0);
  var eo=new Uint8Array(22);
  w4(0x06054b50,eo,0);w2(0,eo,4);w2(0,eo,6);w2(fs.length,eo,8);w2(fs.length,eo,10);
  w4(cs,eo,12);w4(co,eo,16);w2(0,eo,20);
  var all=pts.concat(cds).concat([eo]);
  var tot=all.reduce(function(a,b){return a+b.length;},0),out=new Uint8Array(tot),pos=0;
  all.forEach(function(b){out.set(b,pos);pos+=b.length;});
  return out;
}
async function dlAll(){
  var b=document.getElementById('btn-dl');
  b.textContent='...';b.disabled=true;
  try{
    var d=await fetch('/logs').then(function(r){return r.json();});
    if(!d.files||!d.files.length){alert('Nenhum log.');return;}
    var fs=[];
    for(var i=0;i<d.files.length;i++){
      var fn=d.files[i].name;
      var ab=await fetch('/download?f='+encodeURIComponent(fn)).then(function(r){return r.arrayBuffer();});
      fs.push({name:fn,data:new Uint8Array(ab)});
    }
    var bl=new Blob([_zip(fs)],{type:'application/zip'});
    var a=document.createElement('a');a.href=URL.createObjectURL(bl);a.download='logs.zip';a.click();
  }catch(e){alert('Erro: '+e);}
  finally{b.textContent='\u2B07 Baixar todos';b.disabled=false;}
}

// ── Poll ─────────────────────────────────────────────────────
updSt();setInterval(updSt,3000);
updLog();setInterval(updLog,3000);
</script>
</body></html>
)HTML";

// ── Helpers ───────────────────────────────────────────────────
static const char* _state_name() {
    switch (sm_state()) {
        case State::IDLE:          return "IDLE";
        case State::READY:         return "READY";
        case State::RUNNING_WALK:  return "RUNNING_WALK";
        case State::RUNNING_CLOCK: return "RUNNING_CLOCK";
        case State::RUNNING_BURN:  return "RUNNING_BURN";
        case State::RUNNING_BURN3: return "RUNNING_BURN3";
        case State::FLUSHING:      return "FLUSHING";
        default:                   return "UNKNOWN";
    }
}

static bool _is_running() {
    State s = sm_state();
    return s == State::RUNNING_WALK  || s == State::RUNNING_CLOCK ||
           s == State::RUNNING_BURN  || s == State::RUNNING_BURN3;
}

// Tenta sincronizar NTP (timeout 2 s para não travar o web server)
static void _try_ntp_quick() {
    if (g_epoch_anchored || WiFi.status() != WL_CONNECTED) return;
    configTime(0, 0, "pool.ntp.org", "time.nist.gov");
    struct tm tm_info;
    uint32_t t0 = millis();
    while (!getLocalTime(&tm_info) && millis() - t0 < 2000)
        delay(100);
    if (getLocalTime(&tm_info)) {
        time_t now = mktime(&tm_info);
        csv_write_epoch_anchor((uint32_t)now);
        g_epoch_anchored = true;
        Serial.printf("[NTP] EPOCH_ANCHOR=%lu\n", (unsigned long)now);
    }
}

// Sanitiza nome de arquivo (evita path traversal)
static String _safe_fname(const String& raw) {
    String s = raw;
    s.replace("/", "");
    s.replace("\\", "");
    s.replace("..", "");
    return s;
}

// Resposta JSON simples
static void _json_reply(bool ok, const char* msg_str) {
    String j = "{\"ok\":";
    j += ok ? "true" : "false";
    j += ",\"msg\":\"";
    j += msg_str;
    j += "\"}";
    _srv.send(ok ? 200 : 400, "application/json", j);
}

// ── Rotas HTTP ────────────────────────────────────────────────

// GET / → página de controle
static void _handle_root() {
    _srv.send_P(200, "text/html", _PAGE);
}

// GET /status → JSON com estado atual
static void _handle_status() {
    RunContext* ctx = sm_ctx();

    wifi_ap_record_t ap;
    int8_t rssi = -127;
    if (esp_wifi_sta_get_ap_info(&ap) == ESP_OK) rssi = ap.rssi;

    State st = sm_state();
    String fname = (st != State::IDLE && st != State::READY)
                   ? csv_current_filename() : "";

    uint32_t elapsed_ms = _is_running() ? millis() - ctx->start_ms : 0;

    uint32_t free_kb = csv_free_kb();
    char buf[560];
    snprintf(buf, sizeof(buf),
        "{\"state\":\"%s\","
        "\"cfg\":\"%s/%s/%s\","
        "\"tcp_host\":\"%s\","
        "\"fname\":\"%s\","
        "\"rssi\":%d,"
        "\"temp_c\":%.1f,"
        "\"samples\":%lu,"
        "\"ring\":%u,"
        "\"vin_mv\":%u,"
        "\"flash_kb\":%lu,"
        "\"flash_warn\":%s,"
        "\"flush_warn\":%s,"
        "\"ntp\":%s,"
        "\"elapsed_ms\":%lu,"
        "\"block\":%u,"
        "\"blocks_done\":%u}",
        _state_name(),
        ctx->antenna, ctx->location, ctx->condition,
        g_tcp_host,
        fname.c_str(),
        (int)rssi,
        sup_temp_c(),
        (unsigned long)ctx->samples,
        csv_ring_count(),
        sup_vin_mv(),
        (unsigned long)free_kb,
        (free_kb < FS_WARN_KB) ? "true" : "false",
        g_flush_incomplete ? "true" : "false",
        g_epoch_anchored ? "true" : "false",
        (unsigned long)elapsed_ms,
        ctx->active_block,
        ctx->blocks_done
    );
    _srv.send(200, "application/json", buf);
}

// POST /cmd → executa comando
static void _handle_cmd() {
    String action = _srv.arg("action");

    if (action == "config") {
        String ant = _srv.arg("ant");
        String loc = _srv.arg("loc");
        String cnd = _srv.arg("cnd");
        if (ant.isEmpty() || loc.isEmpty() || cnd.isEmpty()) {
            _json_reply(false, "Preencha antena, local e condicao");
            return;
        }
        const char* err = sm_cmd_config(ant.c_str(), loc.c_str(), cnd.c_str());
        if (err) { _json_reply(false, err); return; }
        // Atualiza alvo TCP se informado
        String tcp = _srv.arg("tcp");
        if (!tcp.isEmpty()) {
            strncpy(g_tcp_host, tcp.c_str(), sizeof(g_tcp_host) - 1);
            g_tcp_host[sizeof(g_tcp_host) - 1] = '\0';
            weblog_printf("[Web] Alvo TCP atualizado: %s\n", g_tcp_host);
        }
        char ok_msg[96];
        snprintf(ok_msg, sizeof(ok_msg), "CONFIG: %s/%s/%s  TCP:%s",
                 ant.c_str(), loc.c_str(), cnd.c_str(), g_tcp_host);
        _json_reply(true, ok_msg);
        return;
    }

    if (action == "start_walk" || action == "start_walk_cold") {
        bool cold = (action == "start_walk_cold");
        const char* err = sm_cmd_start_walk(cold);
        if (err) { _json_reply(false, err); return; }
        _try_ntp_quick();
        digitalWrite(PIN_LED, HIGH);
        String fn = csv_current_filename();
        weblog_printf("[OK] START_WALK%s — %s\n", cold ? " cold" : "", fn.c_str());
        _json_reply(true, (String(cold ? "WALK cold: " : "WALK: ") + fn).c_str());
        return;
    }

    if (action == "start_clock") {
        const char* err = sm_cmd_start_clock();
        if (err) { _json_reply(false, err); return; }
        _try_ntp_quick();
        digitalWrite(PIN_LED, HIGH);
        String fn = csv_current_filename();
        weblog_printf("[OK] START_CLOCK — %s\n", fn.c_str());
        _json_reply(true, (String("CLOCK: ") + fn).c_str());
        return;
    }

    if (action == "start_burn" || action == "start_burn3") {
        // Verificar se o tcp_sink está acessível antes de iniciar
        WiFiClient probe;
        if (!probe.connect(g_tcp_host, TCP_TARGET_PORT, 1500)) {
            weblog_printf("[WARN] tcp_sink nao acessivel em %s:%d\n",
                          g_tcp_host, TCP_TARGET_PORT);
            _json_reply(false,
                "tcp_sink nao esta rodando no notebook. "
                "Execute: python tools/watch.py <IP_NOTEBOOK>");
            return;
        }
        probe.stop();

        bool three = (action == "start_burn3");
        const char* err = sm_cmd_start_burn(three);
        if (err) { _json_reply(false, err); return; }
        _try_ntp_quick();
        digitalWrite(PIN_LED, HIGH);
        String fn = csv_current_filename();
        weblog_printf("[OK] START_BURN%s — %s\n", three ? " 3x60" : "", fn.c_str());
        _json_reply(true, (String(three ? "BURN 3x60: " : "BURN: ") + fn).c_str());
        return;
    }

    if (action == "stop") {
        const char* err = sm_cmd_stop();
        if (err) { _json_reply(false, err); return; }
        weblog_println("[OK] STOP — flush em andamento...");
        _json_reply(true, "Flush em andamento...");
        return;
    }

    if (action == "mark") {
        String label = _srv.arg("label");
        if (label.isEmpty()) { _json_reply(false, "Label vazio"); return; }
        const char* err = sm_cmd_mark(label.c_str());
        if (err) { _json_reply(false, err); return; }
        weblog_printf("[OK] MARK=%s\n", label.c_str());
        _json_reply(true, (String("MARK=") + label).c_str());
        return;
    }

    _json_reply(false, "Acao desconhecida");
}

// GET /logs → JSON com lista de arquivos
static void _handle_logs() {
    File root = LittleFS.open(FS_BASE_PATH);
    String json = "{\"files\":[";
    bool first = true;
    if (root && root.isDirectory()) {
        File f = root.openNextFile();
        while (f) {
            if (!first) json += ",";
            first = false;
            // f.name() retorna só o nome do arquivo no ESP32 Arduino LittleFS
            json += "{\"name\":\"";
            json += f.name();
            json += "\",\"size\":";
            json += (unsigned long)f.size();
            json += "}";
            f = root.openNextFile();
        }
    }
    json += "]}";
    _srv.send(200, "application/json", json);
}

// GET /delete?f=<nome> → apaga o arquivo
static void _handle_delete() {
    String fname = _safe_fname(_srv.arg("f"));
    if (fname.isEmpty()) {
        _json_reply(false, "Param f ausente");
        return;
    }
    String path = String(FS_BASE_PATH) + "/" + fname;
    if (!LittleFS.exists(path)) {
        _json_reply(false, "Arquivo nao encontrado");
        return;
    }
    LittleFS.remove(path);
    _json_reply(true, ("Apagado: " + fname).c_str());
}

// GET /weblog → JSON com buffer circular de log
static void _handle_weblog() {
    static char _wlog_buf[WEBLOG_LINES * (WEBLOG_LINE_LEN + 4) + 32];
    weblog_to_json(_wlog_buf, sizeof(_wlog_buf));
    _srv.send(200, "application/json", _wlog_buf);
}

// GET /download?f=<nome> → stream do CSV
static void _handle_download() {
    String fname = _safe_fname(_srv.arg("f"));
    if (fname.isEmpty()) {
        _srv.send(400, "text/plain", "Param f ausente");
        return;
    }
    String path = String(FS_BASE_PATH) + "/" + fname;
    File f = LittleFS.open(path, "r");
    if (!f) {
        _srv.send(404, "text/plain", "Arquivo nao encontrado: " + path);
        return;
    }
    String disposition = "attachment; filename=\"" + fname + "\"";
    _srv.sendHeader("Content-Disposition", disposition);
    _srv.sendHeader("Content-Length", String(f.size()));
    _srv.streamFile(f, "text/csv");
    f.close();
}

// ── Botão físico ──────────────────────────────────────────────
// Comportamento:
//   READY     → toque curto (< BTN_STOP_HOLD_MS) → START_WALK
//   RUNNING_* → pressão longa (>= BTN_STOP_HOLD_MS) → STOP
//              toque curto durante run → feedback LED, ignora (evita STOP acidental)
#if PIN_BUTTON >= 0
static void _button_poll() {
    static bool     was_pressed = false;
    static uint32_t press_ms    = 0;
    static bool     long_fired  = false;  // evita re-disparo enquanto segura

    bool pressed = (digitalRead(PIN_BUTTON) == LOW);

    if (pressed && !was_pressed) {
        press_ms   = millis();
        was_pressed = true;
        long_fired  = false;
    }

    // Disparo de STOP durante pressão mantida (long press)
    if (pressed && was_pressed && !long_fired) {
        uint32_t held = millis() - press_ms;
        if (held >= BTN_STOP_HOLD_MS && _is_running()) {
            long_fired = true;
            const char* err = sm_cmd_stop();
            if (!err) {
                weblog_println("[BTN] STOP (long press)");
                // Feedback: 6 piscadas rápidas
                for (int i = 0; i < 6; i++) {
                    digitalWrite(PIN_LED, i % 2);
                    delay(80);
                }
            }
        }
    }

    // Release do botão
    if (!pressed && was_pressed) {
        uint32_t held = millis() - press_ms;
        was_pressed   = false;

        if (held < 50) return;  // ruído / bounce

        if (!long_fired) {
            // Toque curto
            State st = sm_state();
            if (st == State::READY) {
                const char* err = sm_cmd_start_walk(false);
                if (!err) {
                    _try_ntp_quick();
                    digitalWrite(PIN_LED, HIGH);
                    weblog_printf("[BTN] START_WALK — %s\n",
                                  csv_current_filename().c_str());
                    for (int i = 0; i < 4; i++) {
                        digitalWrite(PIN_LED, i % 2);
                        delay(60);
                    }
                    digitalWrite(PIN_LED, HIGH);
                }
            } else if (_is_running()) {
                weblog_println("[BTN] Segure para STOP");
                for (int i = 0; i < 2; i++) {
                    digitalWrite(PIN_LED, LOW);
                    delay(100);
                    digitalWrite(PIN_LED, HIGH);
                    delay(100);
                }
            }
        }
    }
}
#endif

// ── API pública ───────────────────────────────────────────────
void web_ui_init() {
    if (_web_started) return;

#if PIN_BUTTON >= 0
    pinMode(PIN_BUTTON, INPUT_PULLUP);
#endif

    _srv.on("/",        HTTP_GET,  _handle_root);
    _srv.on("/status",  HTTP_GET,  _handle_status);
    _srv.on("/weblog",  HTTP_GET,  _handle_weblog);
    _srv.on("/logs",    HTTP_GET,  _handle_logs);
    _srv.on("/download",HTTP_GET,  _handle_download);
    _srv.on("/delete",  HTTP_GET,  _handle_delete);
    _srv.on("/cmd",     HTTP_POST, _handle_cmd);

    _srv.begin();
    _web_started = true;
    weblog_printf("[Web] Painel em http://%s/ (porta %d)\n",
                  WiFi.localIP().toString().c_str(), WEB_UI_PORT);
}

// Inicializa o web server se o WiFi subiu após o boot e ainda não foi iniciado.
// Chamar periodicamente no loop().
void web_ui_try_init() {
    if (!_web_started && WiFi.status() == WL_CONNECTED) {
        web_ui_init();
    }
}

void web_ui_handle() {
    if (!_web_started) return;
    _srv.handleClient();
#if PIN_BUTTON >= 0
    _button_poll();
#endif
}
