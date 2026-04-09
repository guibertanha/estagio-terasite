#include "web_ui.h"
#include "config.h"
#include "state_machine.h"
#include "csv_log.h"   // inclui g_flush_incomplete
#include "supervision.h"
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
body{font-family:monospace;background:#0d1117;color:#c9d1d9;padding:12px;max-width:500px;margin:auto}
h1{color:#58a6ff;font-size:1.05em;margin-bottom:12px;padding:8px;background:#161b22;border-radius:6px;text-align:center}
.card{background:#161b22;border:1px solid #30363d;border-radius:6px;padding:12px;margin-bottom:10px}
.card h3{color:#8b949e;font-size:.8em;text-transform:uppercase;margin-bottom:10px;letter-spacing:.08em}
.sr{display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid #21262d}
.sr:last-child{border-bottom:none}
.sl{color:#8b949e;font-size:.88em}
.sv{color:#e6edf3;font-weight:bold;font-size:.88em}
#sb{display:block;padding:5px;border-radius:4px;font-weight:bold;margin-bottom:10px;text-align:center}
.si{background:#1c1c1c;color:#8b949e}
.sr2{background:#1b2a49;color:#58a6ff}
.sg{background:#1a4731;color:#3fb950}
.sy{background:#2d2016;color:#d29922}
.g3{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-bottom:8px}
label span{font-size:.78em;color:#8b949e;display:block;margin-bottom:2px}
input[type=text]{background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:4px;padding:5px 7px;width:100%;font-family:monospace;font-size:.88em}
input[type=text]:focus{outline:none;border-color:#58a6ff}
button{background:#21262d;color:#c9d1d9;border:1px solid #30363d;border-radius:4px;padding:8px 10px;cursor:pointer;font-family:monospace;font-size:.82em;width:100%}
button:hover{background:#30363d}
.bs{background:#1a4731;color:#3fb950;border-color:#238636}
.bs:hover{background:#238636}
.bx{background:#3d1616;color:#f85149;border-color:#6e2020}
.bx:hover{background:#6e2020}
.bx-arm{background:#6e2020;color:#fff;border-color:#da3633;animation:pulse .4s infinite alternate}
@keyframes pulse{from{opacity:1}to{opacity:.7}}
.bg{display:grid;grid-template-columns:1fr 1fr 1fr;gap:6px;margin-bottom:6px}
.li{display:flex;justify-content:space-between;align-items:center;padding:5px 2px;border-bottom:1px solid #21262d;font-size:.83em}
.li:last-child{border:none}
.la{display:flex;gap:10px;align-items:center}
a{color:#58a6ff;text-decoration:none}
a:hover{text-decoration:underline}
a.del{color:#f85149}
a.del:hover{text-decoration:underline}
.msg{padding:5px 9px;border-radius:4px;margin-top:7px;font-size:.82em;display:none}
.mo{background:#1a4731;color:#3fb950}
.me{background:#3d1616;color:#f85149}
.mw{background:#2d2016;color:#d29922}
.warn-banner{display:none;padding:6px 10px;background:#2d2016;border:1px solid #d29922;border-radius:4px;color:#d29922;font-size:.82em;margin-bottom:8px}
</style>
</head>
<body>
<h1>&#x1F4F6; RF Field Validator N3.0</h1>

<div class="card">
  <div id="sb" class="si">IDLE</div>
  <div id="warn-banner" class="warn-banner">&#x26A0; FLUSH_INCOMPLETE — dados podem estar faltando no CSV</div>
  <div id="timer-row" class="sr" style="display:none"><span class="sl">Tempo</span><span class="sv" id="timer" style="font-size:1.1em;color:#3fb950;letter-spacing:.05em">00:00</span></div>
  <div id="block-row" class="sr" style="display:none"><span class="sl">Bloco</span><span class="sv" id="block-ind" style="color:#d29922">-</span></div>
  <div class="sr"><span class="sl">Config</span><span class="sv" id="cfg">-/-/-</span></div>
  <div class="sr"><span class="sl">Arquivo</span><span class="sv" id="fname" style="font-size:.75em">-</span></div>
  <div class="sr"><span class="sl">RSSI</span><span class="sv" id="rssi">--- dBm</span></div>
  <div class="sr"><span class="sl">Temp</span><span class="sv" id="temp">-- °C</span></div>
  <div class="sr"><span class="sl">Amostras</span><span class="sv" id="samp">0</span></div>
  <div class="sr"><span class="sl">Ring pendente</span><span class="sv" id="ring">0 linhas</span></div>
  <div class="sr"><span class="sl">V_IN</span><span class="sv" id="vin">--- mV</span></div>
  <div class="sr"><span class="sl">Flash livre</span><span class="sv" id="fl">--- KB</span></div>
  <div class="sr"><span class="sl">NTP</span><span class="sv" id="ntp">---</span></div>
</div>

<div class="card">
  <h3>CONFIG</h3>
  <div class="g3">
    <label><span>Antena</span><input type="text" id="ant" value="A1" maxlength="3"></label>
    <label><span>Local</span><input type="text" id="loc" value="TETO" maxlength="5"></label>
    <label><span>Cond.</span><input type="text" id="cnd" value="LIG" maxlength="3"></label>
  </div>
  <button onclick="sendConfig()">Aplicar CONFIG</button>
  <div id="cm" class="msg"></div>
</div>

<div class="card">
  <h3>Controle</h3>
  <div class="bg">
    <button class="bs" onclick="cmd('start_walk')">WALK</button>
    <button class="bs" onclick="cmd('start_walk_cold')">WALK cold</button>
    <button class="bs" onclick="cmd('start_clock')">CLOCK</button>
  </div>
  <div class="bg">
    <button class="bs" onclick="cmd('start_burn')">BURN</button>
    <button class="bs" onclick="cmd('start_burn3')">BURN 3&#xD7;60</button>
    <button id="btn-stop" class="bx" onclick="armStop()">&#x23F9; STOP</button>
  </div>
  <div id="rm" class="msg"></div>
</div>

<div class="card">
  <h3>MARK <span style="font-weight:normal">(s&#xF3; durante CLOCK)</span></h3>
  <div style="display:flex;gap:6px">
    <input type="text" id="mlbl" value="P1" maxlength="8" style="flex:1">
    <button style="width:auto;padding:8px 14px" onclick="sendMark()">Marcar</button>
  </div>
  <div id="mm" class="msg"></div>
</div>

<div class="card">
  <h3>Logs</h3>
  <div style="display:flex;gap:6px;margin-bottom:8px">
    <button style="flex:1" onclick="loadLogs()">&#x21BB; Atualizar lista</button>
    <button id="btn-dl-all" style="flex:1" onclick="downloadAll()">&#x2B07; Baixar todos</button>
  </div>
  <div id="ll"><em style="color:#8b949e;font-size:.83em">Clique em Atualizar lista.</em></div>
</div>

<script>
var SC={IDLE:'si',READY:'sr2',RUNNING_WALK:'sg',RUNNING_CLOCK:'sg',
        RUNNING_BURN:'sg',RUNNING_BURN3:'sg',FLUSHING:'sy'};

var _timerBase=0,_timerRef=0,_timerInterval=null;
function fmtTime(ms){
  var s=Math.floor(ms/1000),m=Math.floor(s/60);s=s%60;
  return(m<10?'0':'')+m+':'+(s<10?'0':'')+s;
}
function startTimer(e){
  _timerBase=e;_timerRef=Date.now();
  document.getElementById('timer-row').style.display='flex';
  if(_timerInterval)clearInterval(_timerInterval);
  _timerInterval=setInterval(function(){
    document.getElementById('timer').textContent=fmtTime(_timerBase+(Date.now()-_timerRef));
  },1000);
}
function stopTimer(){
  if(_timerInterval){clearInterval(_timerInterval);_timerInterval=null;}
  document.getElementById('timer-row').style.display='none';
  document.getElementById('timer').textContent='00:00';
}

function msg(id,ok,t,warn){
  var e=document.getElementById(id);
  e.className='msg '+(warn?'mw':ok?'mo':'me');
  e.textContent=t;e.style.display='block';
  setTimeout(function(){e.style.display='none';},3500);
}

function post(b,cb){
  fetch('/cmd',{method:'POST',
    headers:{'Content-Type':'application/x-www-form-urlencoded'},body:b})
  .then(function(r){return r.json();}).then(cb)
  .catch(function(e){cb({ok:false,msg:'Erro de rede'});});
}

function cmd(a){post('action='+a,function(r){msg('rm',r.ok,r.msg);});}

// ── STOP com confirmação de 2 toques ─────────────────────────
var _stopArmed=false,_stopTimer=null;
function armStop(){
  var btn=document.getElementById('btn-stop');
  if(!_stopArmed){
    _stopArmed=true;
    btn.textContent='Toque de novo para CONFIRMAR';
    btn.className='bx bx-arm';
    _stopTimer=setTimeout(function(){
      _stopArmed=false;
      btn.textContent='&#x23F9; STOP';
      btn.className='bx';
    },3000);
  } else {
    clearTimeout(_stopTimer);
    _stopArmed=false;
    btn.textContent='&#x23F9; STOP';
    btn.className='bx';
    post('action=stop',function(r){msg('rm',r.ok,r.msg);});
  }
}

function sendConfig(){
  var a=document.getElementById('ant').value.trim();
  var l=document.getElementById('loc').value.trim();
  var c=document.getElementById('cnd').value.trim();
  post('action=config&ant='+encodeURIComponent(a)
      +'&loc='+encodeURIComponent(l)+'&cnd='+encodeURIComponent(c),
    function(r){msg('cm',r.ok,r.msg);});
}

function sendMark(){
  var m=document.getElementById('mlbl').value.trim();
  post('action=mark&label='+encodeURIComponent(m),
    function(r){msg('mm',r.ok,r.msg);});
}

function loadLogs(){
  fetch('/logs').then(function(r){return r.json();}).then(function(d){
    var h='';
    if(d.files&&d.files.length){
      d.files.forEach(function(f){
        var kb=(f.size/1024).toFixed(1);
        var enc=encodeURIComponent(f.name);
        h+='<div class="li"><span>'+f.name+'<br>'
          +'<span style="color:#8b949e">'+kb+' KB</span></span>'
          +'<div class="la">'
          +'<a href="/download?f='+enc+'">baixar</a>'
          +'<a class="del" href="#" onclick="delFile(\''+enc+'\');return false;">apagar</a>'
          +'</div></div>';
      });
    } else {
      h='<em style="color:#8b949e;font-size:.83em">Nenhum log encontrado.</em>';
    }
    document.getElementById('ll').innerHTML=h;
  }).catch(function(){
    document.getElementById('ll').innerHTML='<em style="color:#f85149">Erro ao listar logs.</em>';
  });
}

function delFile(enc){
  if(!confirm('Apagar '+decodeURIComponent(enc)+'?'))return;
  fetch('/delete?f='+enc).then(function(r){return r.json();}).then(function(d){
    if(d.ok)loadLogs();else alert('Erro: '+d.msg);
  }).catch(function(){alert('Erro de rede');});
}

// ── ZIP STORE mode (sem compressão, sem dependências) ─────────
var _crcT=(function(){var t=[];for(var i=0;i<256;i++){var c=i;for(var j=0;j<8;j++)c=c&1?(0xEDB88320^(c>>>1)):c>>>1;t[i]=c>>>0;}return t;})();
function _crc32(u8){var c=0xFFFFFFFF;for(var i=0;i<u8.length;i++)c=(_crcT[(c^u8[i])&0xFF]^(c>>>8))>>>0;return(c^0xFFFFFFFF)>>>0;}
function _zip(files){
  function w32(v,b,o){b[o]=v&0xFF;b[o+1]=(v>>8)&0xFF;b[o+2]=(v>>16)&0xFF;b[o+3]=(v>>24)&0xFF;}
  function w16(v,b,o){b[o]=v&0xFF;b[o+1]=(v>>8)&0xFF;}
  var parts=[],cdirs=[],off=0,enc=new TextEncoder();
  files.forEach(function(f){
    var nm=enc.encode(f.name),d=f.data,crc=_crc32(d),sz=d.length;
    var lh=new Uint8Array(30+nm.length);
    w32(0x04034b50,lh,0);w16(20,lh,4);w16(0,lh,6);w16(0,lh,8);w16(0,lh,10);w16(0,lh,12);
    w32(crc,lh,14);w32(sz,lh,18);w32(sz,lh,22);w16(nm.length,lh,26);w16(0,lh,28);lh.set(nm,30);
    var cd=new Uint8Array(46+nm.length);
    w32(0x02014b50,cd,0);w16(20,cd,4);w16(20,cd,6);w16(0,cd,8);w16(0,cd,10);w16(0,cd,12);w16(0,cd,14);
    w32(crc,cd,16);w32(sz,cd,20);w32(sz,cd,24);w16(nm.length,cd,28);w16(0,cd,30);w16(0,cd,32);
    w16(0,cd,34);w16(0,cd,36);w32(0,cd,38);w32(off,cd,42);cd.set(nm,46);
    parts.push(lh,d);cdirs.push(cd);off+=lh.length+sz;
  });
  var cdOff=off,cdSz=cdirs.reduce(function(a,c){return a+c.length;},0);
  var eocd=new Uint8Array(22);
  w32(0x06054b50,eocd,0);w16(0,eocd,4);w16(0,eocd,6);w16(files.length,eocd,8);w16(files.length,eocd,10);
  w32(cdSz,eocd,12);w32(cdOff,eocd,16);w16(0,eocd,20);
  var all=parts.concat(cdirs).concat([eocd]);
  var tot=all.reduce(function(a,b){return a+b.length;},0),out=new Uint8Array(tot),pos=0;
  all.forEach(function(b){out.set(b,pos);pos+=b.length;});
  return out;
}
async function downloadAll(){
  var btn=document.getElementById('btn-dl-all');
  btn.textContent='...';btn.disabled=true;
  try{
    var d=await fetch('/logs').then(function(r){return r.json();});
    if(!d.files||!d.files.length){alert('Nenhum log.');return;}
    var files=[];
    for(var i=0;i<d.files.length;i++){
      var fn=d.files[i].name;
      var ab=await fetch('/download?f='+encodeURIComponent(fn)).then(function(r){return r.arrayBuffer();});
      files.push({name:fn,data:new Uint8Array(ab)});
    }
    var blob=new Blob([_zip(files)],{type:'application/zip'});
    var a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='logs.zip';a.click();
  }catch(e){alert('Erro: '+e);}
  finally{btn.textContent='&#x2B07; Baixar todos';btn.disabled=false;}
}

var _wasRunning=false;
function updateStatus(){
  fetch('/status').then(function(r){return r.json();}).then(function(d){
    var sb=document.getElementById('sb');
    sb.textContent=d.state;
    sb.className=SC[d.state]||'si';
    document.getElementById('cfg').textContent=d.cfg;
    document.getElementById('fname').textContent=d.fname||'-';
    document.getElementById('rssi').textContent=d.rssi+' dBm';
    document.getElementById('temp').textContent=d.temp_c!=null?d.temp_c.toFixed(1)+' \u00b0C':'--';
    document.getElementById('samp').textContent=d.samples;
    document.getElementById('ring').textContent=d.ring+' linhas';

    // V_IN — sem cor especial (ADC pode não estar conectado)
    document.getElementById('vin').textContent=d.vin_mv>0?d.vin_mv+' mV':'-- (sem sensor)';

    // Flash — vermelho quando abaixo do threshold de aviso
    var flEl=document.getElementById('fl');
    flEl.textContent=d.flash_kb+' KB';
    flEl.style.color=d.flash_warn?'#f85149':'#e6edf3';

    document.getElementById('ntp').textContent=d.ntp?'ancorado':'nao ancorado';

    // Banner de FLUSH_INCOMPLETE
    document.getElementById('warn-banner').style.display=d.flush_warn?'block':'none';

    var running=d.elapsed_ms>0;
    if(running){startTimer(d.elapsed_ms);}
    else if(_wasRunning){stopTimer();}
    _wasRunning=running;

    var blkRow=document.getElementById('block-row');
    if(d.state==='RUNNING_BURN3'){
      blkRow.style.display='flex';
      document.getElementById('block-ind').textContent=(d.block||1)+'/3';
    }else{blkRow.style.display='none';}
  }).catch(function(){});
}

updateStatus();
setInterval(updateStatus,3000);
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
    char buf[480];
    snprintf(buf, sizeof(buf),
        "{\"state\":\"%s\","
        "\"cfg\":\"%s/%s/%s\","
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
        char ok_msg[64];
        snprintf(ok_msg, sizeof(ok_msg), "CONFIG: %s/%s/%s", ant.c_str(), loc.c_str(), cnd.c_str());
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
        String m = String(cold ? "WALK cold: " : "WALK: ") + fn;
        _json_reply(true, m.c_str());
        return;
    }

    if (action == "start_clock") {
        const char* err = sm_cmd_start_clock();
        if (err) { _json_reply(false, err); return; }
        _try_ntp_quick();
        digitalWrite(PIN_LED, HIGH);
        String m = String("CLOCK: ") + csv_current_filename();
        _json_reply(true, m.c_str());
        return;
    }

    if (action == "start_burn" || action == "start_burn3") {
        bool three = (action == "start_burn3");
        const char* err = sm_cmd_start_burn(three);
        if (err) { _json_reply(false, err); return; }
        _try_ntp_quick();
        digitalWrite(PIN_LED, HIGH);
        String m = String(three ? "BURN 3x60: " : "BURN: ") + csv_current_filename();
        _json_reply(true, m.c_str());
        return;
    }

    if (action == "stop") {
        const char* err = sm_cmd_stop();
        if (err) { _json_reply(false, err); return; }
        _json_reply(true, "Flush em andamento...");
        return;
    }

    if (action == "mark") {
        String label = _srv.arg("label");
        if (label.isEmpty()) { _json_reply(false, "Label vazio"); return; }
        const char* err = sm_cmd_mark(label.c_str());
        if (err) { _json_reply(false, err); return; }
        String m = String("MARK=") + label;
        _json_reply(true, m.c_str());
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
                Serial.println("[BTN] STOP (long press)");
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
                    Serial.printf("[BTN] START_WALK — %s\n",
                                  csv_current_filename().c_str());
                    for (int i = 0; i < 4; i++) {
                        digitalWrite(PIN_LED, i % 2);
                        delay(60);
                    }
                    digitalWrite(PIN_LED, HIGH);
                }
            } else if (_is_running()) {
                // Toque curto durante run → feedback de aviso (não para o run)
                Serial.println("[BTN] Segure para STOP");
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
    _srv.on("/logs",    HTTP_GET,  _handle_logs);
    _srv.on("/download",HTTP_GET,  _handle_download);
    _srv.on("/delete",  HTTP_GET,  _handle_delete);
    _srv.on("/cmd",     HTTP_POST, _handle_cmd);

    _srv.begin();
    _web_started = true;
    Serial.printf("[Web] Painel em http://%s/ (porta %d)\n",
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
