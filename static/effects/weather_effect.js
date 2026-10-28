const box = document.getElementById("weather_effect");

/* Sozlamalardan öqiş */
const savedEffect = localStorage.getItem('weatherEffect') || 'auto';
console.log('Weather effect setting:', savedEffect);

/* Agar öçirilgan bölsa, box ni yaşiramiz va töxtatamiz */
if (savedEffect === 'off') {
    console.log('Weather OFF - hiding box');
    if (box) {
        box.style.display = 'none';
        box.innerHTML = '';
    }
} else {
    let season;
    
    if (savedEffect === 'auto') {
        /* fasl aniqlaş */
        const m = new Date().getMonth() + 1;
        season = "winter";
        
        if(m>=3 && m<=5) season="spring";
        else if(m>=6 && m<=8) season="summer";
        else if(m>=9 && m<=11) season="autumn";
    } else {
        /* Foydalanuvçi tanlagan */
        season = savedEffect;
    }
    
    /* emoji va class */
    const effects = {
      winter: ["❄","✻","❅","•"],
      spring: ["|"],        // rain drop
      summer: ["☀","🌤"],
      autumn: ["🍁","🍂","🍃"]
    };
    
    function createWeather(){
      if(!box) return;
    
      const el = document.createElement("div");
      el.classList.add("weather-item", season);
    
      el.innerHTML = effects[season][Math.floor(Math.random()*effects[season].length)];
    
      const size = Math.random()*14 + 10;
      el.style.fontSize = size + "px";
      el.style.left = Math.random()*100 + "vw";
    
      const fallTime = Math.random()*5 + 6;
      el.style.animationDuration = `${fallTime}s, 3s, 2s`;
    
      box.appendChild(el);
      setTimeout(()=>el.remove(), fallTime*1000);
    }
    
    /* intensivlik */
    let density = 180;
    if(season==="spring") density = 120;
    if(season==="summer") density = 350;
    if(season==="autumn") density = 200;
    
    setInterval(createWeather, density);
}

/* ===== PAGE LOADER ===== */
window.addEventListener("load",()=>{
  const loader = document.getElementById("pageLoader");
  if(loader){
    loader.style.opacity="1";
    setTimeout(()=>loader.remove(),600);
  }
});
