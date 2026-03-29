<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>SpotEasy — Starting Up...</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@600;700;800;900&display=swap" rel="stylesheet"/>
<style>
*{margin:0;padding:0;box-sizing:border-box;font-family:'Inter',sans-serif;}
body{background:#0a0d14;color:white;min-height:100vh;display:flex;align-items:center;justify-content:center;padding:16px;}

/* Animated grid background like Render but green */
.grid-bg{position:fixed;inset:0;z-index:0;background-image:linear-gradient(rgba(34,197,94,0.06) 1px,transparent 1px),linear-gradient(90deg,rgba(34,197,94,0.06) 1px,transparent 1px);background-size:60px 60px;}
.grid-fade{position:fixed;inset:0;z-index:1;background:radial-gradient(ellipse at center,transparent 0%,#0a0d14 70%);}

/* Floating particles */
.particles{position:fixed;inset:0;z-index:2;overflow:hidden;pointer-events:none;}
@keyframes rise{from{transform:translateY(100vh) scale(0);opacity:0}to{transform:translateY(-10vh) scale(1);opacity:0.15}}
.p{position:absolute;border-radius:50%;background:#22c55e;animation:rise linear infinite;}

/* Card */
.wrap{position:relative;z-index:10;width:100%;max-width:480px;}

/* Top status bar (like Render's terminal) */
.terminal{background:#0f1117;border:1px solid rgba(34,197,94,0.2);border-radius:16px 16px 0 0;padding:16px 20px;font-family:'Courier New',monospace;font-size:12px;color:#6b7280;margin-bottom:0;min-height:80px;}
.terminal-line{margin-bottom:6px;display:flex;gap:10px;align-items:baseline;}
.terminal-time{color:#374151;font-size:11px;min-width:55px;}
.terminal-msg{color:#22c55e;}
@keyframes blink{0%,100%{opacity:1}50%{opacity:0}}
.cursor{display:inline-block;width:8px;height:13px;background:#22c55e;animation:blink 1s infinite;vertical-align:text-bottom;margin-left:4px;}

/* Main card */
.card{background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-top:none;border-radius:0 0 24px 24px;padding:24px;}

/* Logo */
.logo-wrap{display:flex;align-items:center;gap:12px;margin-bottom:20px;}
.logo{width:52px;height:52px;background:linear-gradient(135deg,#16a34a,#22c55e);border-radius:16px;display:flex;align-items:center;justify-content:center;font-size:26px;flex-shrink:0;box-shadow:0 0 30px rgba(34,197,94,0.35);}
.logo-text h1{font-size:20px;font-weight:900;margin-bottom:2px;}
.logo-text p{font-size:12px;color:#6b7280;}

/* Progress */
.prog-wrap{background:rgba(255,255,255,0.06);border-radius:99px;height:6px;overflow:hidden;margin-bottom:6px;}
.prog-bar{height:6px;background:linear-gradient(90deg,#16a34a,#4ade80);border-radius:99px;width:5%;transition:width 0.8s ease;}
.prog-txt{font-size:11px;color:#4ade80;font-weight:700;margin-bottom:20px;}

/* Divider */
.div{border:none;border-top:1px solid rgba(255,255,255,0.07);margin:16px 0;}

/* Quiz */
.q-label{font-size:10px;font-weight:800;color:#4b5563;text-transform:uppercase;letter-spacing:1px;margin-bottom:10px;}
.q-text{font-size:14px;font-weight:800;color:#f1f5f9;margin-bottom:12px;line-height:1.5;min-height:42px;}
.q-opts{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-bottom:10px;}
.opt{background:rgba(255,255,255,0.05);border:1.5px solid rgba(255,255,255,0.1);border-radius:12px;padding:10px 8px;font-size:12px;font-weight:600;color:#d1d5db;cursor:pointer;text-align:center;width:100%;line-height:1.3;transition:all 0.15s;}
.opt:hover{background:rgba(34,197,94,0.12);border-color:#22c55e;color:white;}
.opt.correct{background:rgba(34,197,94,0.2)!important;border-color:#4ade80!important;color:#4ade80!important;}
.opt.wrong{background:rgba(239,68,68,0.15)!important;border-color:#f87171!important;color:#f87171!important;}
.opt.reveal{background:rgba(34,197,94,0.12)!important;border-color:#22c55e!important;color:#4ade80!important;}

.q-footer{display:flex;justify-content:space-between;align-items:center;font-size:11px;}
.q-num{color:#4b5563;}
.q-score{background:rgba(34,197,94,0.15);border:1px solid rgba(34,197,94,0.3);color:#4ade80;font-weight:800;padding:2px 10px;border-radius:99px;}
.fact{background:rgba(34,197,94,0.06);border:1px solid rgba(34,197,94,0.15);border-radius:10px;padding:10px 12px;font-size:11px;color:#86efac;line-height:1.6;margin-top:10px;display:none;}

/* Tip ticker */
.tip{background:rgba(255,255,255,0.03);border-radius:10px;padding:10px 12px;font-size:11px;color:#6b7280;text-align:center;margin-top:14px;}
.tip b{color:#4ade80;}
</style>
</head>
<body>

<div class="grid-bg"></div>
<div class="grid-fade"></div>
<div class="particles" id="parts"></div>

<div class="wrap">
  <!-- Terminal header (like Render's UI) -->
  <div class="terminal" id="terminal">
    <div class="terminal-line">
      <span class="terminal-time" id="t1"></span>
      <span class="terminal-msg">INCOMING HTTP REQUEST DETECTED ...</span>
    </div>
    <div class="terminal-line" id="tl2" style="display:none;">
      <span class="terminal-time" id="t2"></span>
      <span class="terminal-msg">SERVICE WAKING UP ...</span>
    </div>
    <div class="terminal-line" id="tl3" style="display:none;">
      <span class="terminal-time" id="t3"></span>
      <span class="terminal-msg">STARTING SPOTEASY INDIA ...<span class="cursor"></span></span>
    </div>
  </div>

  <!-- Main card -->
  <div class="card">
    <div class="logo-wrap">
      <div class="logo">🅿️</div>
      <div class="logo-text">
        <h1>SpotEasy India</h1>
        <p>Smart Parking &bull; Waking up server...</p>
      </div>
    </div>

    <div class="prog-wrap"><div class="prog-bar" id="progBar"></div></div>
    <div class="prog-txt" id="progTxt">Connecting to server...</div>

    <hr class="div"/>

    <!-- Quiz -->
    <div class="q-label">🧠 Answer while you wait!</div>
    <div class="q-text" id="qText">Loading question...</div>
    <div class="q-opts" id="qOpts"></div>
    <div class="q-footer">
      <span class="q-num" id="qNum">Question 1/5</span>
      <span class="q-score" id="qScore">Score: 0</span>
    </div>
    <div class="fact" id="factEl"></div>
    <div class="tip" id="tipEl">💡 SpotEasy — Smart Parking for India</div>
  </div>
</div>

<script>
// Particles
var parts = document.getElementById('parts');
for(var i=0;i<14;i++){
  var p=document.createElement('div');
  p.className='p';
  var s=Math.random()*60+15;
  p.style.cssText='width:'+s+'px;height:'+s+'px;left:'+Math.random()*100+'%;animation-duration:'+(Math.random()*10+8)+'s;animation-delay:'+(Math.random()*8)+'s;';
  parts.appendChild(p);
}

// Terminal time
function nowTime(){return new Date().toLocaleTimeString('en-GB',{hour12:false});}
document.getElementById('t1').textContent=nowTime();
setTimeout(function(){
  document.getElementById('tl2').style.display='flex';
  document.getElementById('t2').textContent=nowTime();
},2000);
setTimeout(function(){
  document.getElementById('tl3').style.display='flex';
  document.getElementById('t3').textContent=nowTime();
},4000);

// Quiz data
var QS=[
  {q:'What is SpotEasy\'s free grace period?',opts:['5 mins','10 mins','15 mins','30 mins'],ans:2,fact:'SpotEasy gives 15 minutes free! Exit within 15 mins → zero charge.'},
  {q:'UPI stands for?',opts:['United Payment Interface','Unified Payments Interface','Universal Pay Index','Unique Payment ID'],ans:1,fact:'UPI processes 10+ billion transactions monthly in India!'},
  {q:'PWA stands for?',opts:['Private Web App','Progressive Web App','Premium Web Access','Public Web App'],ans:1,fact:'SpotEasy is a PWA — install it without any App Store!'},
  {q:'Which city has India\'s worst parking problem?',opts:['Delhi','Mumbai','Bengaluru','Chennai'],ans:2,fact:'Bengaluru has 1 crore+ vehicles but parking for only 20 lakh!'},
  {q:'SpotEasy supports which payments?',opts:['Only Cash','Only UPI','Cash & UPI','Card Only'],ans:2,fact:'SpotEasy supports both Cash and UPI — easy and contactless!'},
  {q:'What does IoT stand for?',opts:['Internet of Things','Index of Technology','Interface of Tools','Intranet of Things'],ans:0,fact:'IoT sensors can auto-detect parking slot availability!'},
  {q:'How many cars are sold in India per year?',opts:['10 Lakh','25 Lakh','42 Lakh','70 Lakh'],ans:2,fact:'India sells ~42 lakh cars annually — smart parking is critical!'},
];
var TIPS=['💡 Use <b>UPI</b> for instant contactless payment','🔔 Enable <b>notifications</b> for booking alerts','📱 SpotEasy works <b>offline</b> after install!','⏱️ <b>Grace period</b> — exit in 15 mins, pay nothing!','🗺️ Use <b>Find Parking</b> to see nearest lots on map'];
var STAGES=[
  {p:10,m:'🌐 Connecting to server...'},
  {p:22,m:'🗄️ Waking up database...'},
  {p:36,m:'🔧 Loading application...'},
  {p:50,m:'🗺️ Fetching parking data...'},
  {p:64,m:'🔐 Setting up security...'},
  {p:76,m:'📱 Preparing your experience...'},
  {p:87,m:'🎯 Almost ready...'},
  {p:94,m:'✨ Finalizing...'},
];

// Shuffle + pick 5
var shuffled=QS.slice().sort(function(){return Math.random()-0.5;}).slice(0,5);
var qIdx=0,score=0,answered=false;

function loadQ(){
  if(qIdx>=shuffled.length){
    document.getElementById('qText').textContent='Quiz done! Score: '+score+'/'+shuffled.length+' '+(score>=4?'🏆':score>=2?'👍':'💪');
    document.getElementById('qOpts').innerHTML='<div style="grid-column:1/-1;text-align:center;padding:12px;font-size:13px;color:#4ade80;font-weight:800;">Server is almost ready...</div>';
    return;
  }
  answered=false;
  var q=shuffled[qIdx];
  document.getElementById('qText').textContent=q.q;
  document.getElementById('qNum').textContent='Question '+(qIdx+1)+'/'+shuffled.length;
  document.getElementById('factEl').style.display='none';
  var d=document.getElementById('qOpts');
  d.innerHTML='';
  q.opts.forEach(function(o,i){
    var b=document.createElement('button');
    b.className='opt';b.textContent=o;
    b.onclick=function(){pick(i,b);};
    d.appendChild(b);
  });
}

function pick(i,btn){
  if(answered)return;
  answered=true;
  var q=shuffled[qIdx];
  document.querySelectorAll('.opt').forEach(function(b){b.disabled=true;});
  if(i===q.ans){btn.classList.add('correct');score++;document.getElementById('qScore').textContent='Score: '+score+' ✅';}
  else{btn.classList.add('wrong');document.querySelectorAll('.opt')[q.ans].classList.add('reveal');}
  var f=document.getElementById('factEl');
  f.textContent='💡 '+q.fact;f.style.display='block';
  setTimeout(function(){qIdx++;loadQ();},2800);
}

// Progress
var si=0;
function nextStage(){
  if(si<STAGES.length){var s=STAGES[si++];document.getElementById('progBar').style.width=s.p+'%';document.getElementById('progTxt').textContent=s.m;}
}
nextStage();
var pt=setInterval(nextStage,5000);

// Tips
var ti=0;
function rotateTip(){document.getElementById('tipEl').innerHTML=TIPS[ti++%TIPS.length];}
rotateTip();setInterval(rotateTip,4000);

// Poll server
var attempts=0;
var dest=new URLSearchParams(window.location.search).get('next')||'/';

function poll(){
  attempts++;
  fetch('/health',{cache:'no-store',signal:AbortSignal.timeout(6000)})
    .then(function(r){if(r.ok)return r.json();throw 0;})
    .then(function(){
      clearInterval(pt);
      document.getElementById('progBar').style.width='100%';
      document.getElementById('progTxt').textContent='✅ SpotEasy is ready! Redirecting...';
      setTimeout(function(){window.location.href=dest;},700);
    })
    .catch(function(){
      if(attempts<90)setTimeout(poll,2000);
      else window.location.href=dest;
    });
}
setTimeout(poll,1500);
loadQ();
</script>
</body>
</html>
