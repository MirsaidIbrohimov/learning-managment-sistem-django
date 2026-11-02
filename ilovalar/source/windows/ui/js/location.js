// Kirişdan keyingi joylaşuv (saytdagi "Joylaşuvni ulaşiş" bilan bir xil maqsad): foydalanuvçi roziligi bilan
// koordinata serverga yuboriladi va admin panelda "Windows ilova" belgisi bilan körinadi.
// Bir marta ruxsat berilsa — keyingi kirişlarda qayta söralmaydi, joylaşuv jim yoziladi.
import { api } from './api.js';
import { icon } from './icons.js';
import { modal, toast, esc } from './ui.js';

const key = (uid) => `itc.location.${uid}`;
const read = (uid) => { try { return JSON.parse(localStorage.getItem(key(uid))) || {}; } catch { return {}; } };
const write = (uid, v) => localStorage.setItem(key(uid), JSON.stringify({ ...v, at: Date.now() }));

function position() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) { reject(Object.assign(new Error('unsupported'), { code: -1 })); return; }
    navigator.geolocation.getCurrentPosition(resolve, reject, { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 });
  });
}

async function capture(user, { silent }) {
  try {
    const pos = await position();
    const r = await api.post('/api/v1/app/location/', {
      latitude: pos.coords.latitude,
      longitude: pos.coords.longitude,
      accuracy: pos.coords.accuracy,
    });
    write(user.id, { state: 'granted' });
    if (!silent) toast(r?.address ? `Joylaşuv saqlandi: ${r.address}` : 'Joylaşuv saqlandi');
  } catch (e) {
    if (e?.code === 1) {
      // Foydalanuvçi yoki Windows ruxsat bermadi — keyingi kirişda yana söraymiz
      write(user.id, { state: 'declined' });
      if (!silent) toast("Joylaşuvga ruxsat berilmadi. Windows sozlamalarida (Maxfiylik → Joylaşuv) ilovalarga ruxsatni yoqing.", 'err', 6000);
    } else if (!silent) {
      toast("Joylaşuvni aniqlab bölmadi. Keyinroq qayta urinib köramiz.", 'err');
    }
  }
}

/** Faqat yangi kirişdan keyin çaqiriladi (saqlangan sessiya bilan oçilganda emas). */
export function afterLogin(user) {
  if (!user?.id) return;
  if (read(user.id).state === 'granted') { capture(user, { silent: true }); return; }
  setTimeout(() => {
    const m = modal({
      title: 'Joylaşuvingizni ulaşasizmi?',
      content: `
        <div class="loc-ask">
          <div class="loc-ico">${icon('target')}</div>
          <p>Hisobingiz xavfsizligi uçun kiriş qayerdan bölganini saqlaymiz. Joylaşuv faqat sizning roziligingiz bilan,
          faqat kiriş paytida olinadi va hisobingizdagi kirişlar tarixida körinadi.</p>
          <div class="loc-note">${icon('shield')}<span>Bir marta ruxsat bersangiz, keyingi kirişlarda qayta söralmaydi. Istalgan payt Windows sozlamalaridan öçirişingiz mumkin.</span></div>
        </div>`,
      foot: `<button class="btn" data-close>Keyinroq</button><button class="btn btn-primary" id="loc-allow">${icon('target')} Joylaşuvni ulaşiş</button>`,
    });
    m.el.querySelector('#loc-allow').addEventListener('click', async (e) => {
      e.currentTarget.disabled = true;
      e.currentTarget.innerHTML = `${icon('loader', 'spin')} ${esc('Aniqlanmoqda…')}`;
      await capture(user, { silent: false });
      m.close();
    });
  }, 700);
}
