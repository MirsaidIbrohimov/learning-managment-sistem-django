/* DEMO MA'LUMOTLAR — faqat prototip uçun. Real bazaga bog'lanmagan.
   Maydon nomlari real Django context kalitlariga mos tanlangan (izohlarda körsatilgan),
   integratsiyada aynan şu kalitlar view'dan keladi. */
window.DP_DATA = (function () {
  'use strict';

  var admin = {
    user: { name: 'Husanbek Suyunov', first: 'Husanbek', role: 'Administrator', initials: 'HS' },
    // accounts.views.admin_dashboard -> total_students, total_teachers, total_professions ...
    stats: {
      total_students: 1248, total_teachers: 36, total_professions: 18, total_groups: 74,
      online_users: 87, total_parents: 690, total_certificates: 412,
      pending_homeworks: 57, avg_test_score: 78.4, passed_tests: 3120, total_test_results: 3986,
      blocked_users: 9
    },
    // finance / growth dict'lari
    finance: { month_revenue: 186400000, prev_revenue: 166300000, revenue_change: 12,
               month_paid_count: 712, month_unpaid: 23600000, month_unpaid_count: 41 },
    growth: { new_this_month: 164, new_prev_month: 150, user_change: 9 },
    // daily_stats (7 kun) — users + enrollments
    trend: {
      '7': { labels: ['Du', 'Se', 'Çor', 'Pay', 'Ju', 'Şa', 'Ya'],
             users: [18, 24, 21, 30, 27, 35, 22], enroll: [12, 15, 19, 22, 18, 29, 16] },
      '30': { labels: ['1-hafta', '2-hafta', '3-hafta', '4-hafta'],
              users: [96, 121, 108, 142], enroll: [74, 88, 95, 117] },
      '180': { labels: ['Iyun', 'Iyul', 'Avg', 'Sen', 'Okt', 'Noy'],
               users: [310, 342, 298, 455, 520, 164], enroll: [240, 276, 251, 398, 461, 139] }
    },
    revenueMonths: { labels: ['Iyun', 'Iyul', 'Avg', 'Sen', 'Okt', 'Noy'],
                     values: [142, 151, 138, 171, 166, 186] }, // mln söm
    // course_perf (TOP)
    courses: [
      { name: 'Frontend (React)', students: 212, lessons: 96, pending: 12, avg: 81.2, color: 1 },
      { name: 'Python Backend', students: 186, lessons: 88, pending: 9, avg: 77.5, color: 2 },
      { name: 'Grafik dizayn', students: 164, lessons: 64, pending: 7, avg: 84.1, color: 3 },
      { name: 'Ingliz tili (IELTS)', students: 241, lessons: 120, pending: 15, avg: 72.8, color: 4 },
      { name: 'Kompyuter savodxonligi', students: 198, lessons: 40, pending: 3, avg: 88.6, color: 1 },
      { name: 'Mobil dasturlaş (Flutter)', students: 97, lessons: 72, pending: 6, avg: 74.3, color: 2 },
      { name: 'Robototexnika', students: 84, lessons: 48, pending: 5, avg: 79.9, color: 3 }
    ],
    activities: [
      { who: 'Dilnoza Karimova', what: '«Python Backend» kursiga yozildi', when: '3 daqiqa oldin', icon: 'person-plus', tone: 'info' },
      { who: 'Jasur Aliyev', what: 'Noyabr oyi uçun 450 000 söm töladi', when: '12 daqiqa oldin', icon: 'credit-card', tone: 'success' },
      { who: 'Aziza Tursunova', what: 'FE-24 guruhida davomatni belgiladi', when: '28 daqiqa oldin', icon: 'calendar-check', tone: 'accent' },
      { who: 'Bekzod Nazarov', what: 'Yakuniy testdan 92% oldi', when: '1 soat oldin', icon: 'patch-check', tone: 'success' },
      { who: 'Tizim', what: '3 ta qurilma limiti oşgan hisob bloklandi', when: '2 soat oldin', icon: 'shield-exclamation', tone: 'danger' },
      { who: 'Malika Yusupova', what: 'Kursdan çiqiş sörovini yubordi', when: '3 soat oldin', icon: 'box-arrow-right', tone: 'warning' }
    ],
    attention: [
      { label: 'Tekşirilmagan vazifalar', value: 57, icon: 'journal-check', tone: 'warning' },
      { label: 'Kursga yoziliş sörovlari', value: 14, icon: 'inbox', tone: 'info' },
      { label: 'Qarzdor öquvçilar', value: 41, icon: 'exclamation-circle', tone: 'danger' },
      { label: 'Yordam xatlari', value: 5, icon: 'life-preserver', tone: 'accent' }
    ]
  };

  var first = ['Dilnoza', 'Jasur', 'Bekzod', 'Malika', 'Sardor', 'Nodira', 'Otabek', 'Shahzoda', 'Ulug\'bek', 'Kamola', 'Doniyor', 'Madina', 'Azamat', 'Sevara', 'Javohir', 'Zarina', 'Islom', 'Gulnoza', 'Temur', 'Laylo', 'Abdulloh', 'Munisa', 'Sanjar', 'Hilola'];
  var last = ['Karimova', 'Aliyev', 'Nazarov', 'Yusupova', 'Rahimov', 'Qodirova', 'Ergashev', 'Sobirova', 'Tursunov', 'Ismoilova', 'Hasanov', 'Raximova', 'Mirzayev', 'Olimova', 'Saidov', 'Abdullayeva', 'Suyunov', 'Xolmatova', 'Jurayev', 'Normatova', 'Usmonov', 'Ahmedova', 'Toirov', 'Valiyeva'];
  var courseNames = admin.courses.map(function (c) { return c.name; });
  var groups = ['FE-24', 'PY-11', 'GD-07', 'EN-31', 'KS-02', 'FL-05', 'RB-03'];
  var pay = ['paid', 'paid', 'debt', 'paid', 'contract', 'paid', 'debt', 'paid'];
  var seen = ['hozir onlayn', '5 daqiqa oldin', '1 soat oldin', 'kecha', '2 kun oldin', '1 hafta oldin'];
  admin.students = first.map(function (f, i) {
    var ci = (i * 3) % courseNames.length;
    return {
      id: 1000 + i, name: f + ' ' + last[i], initials: f[0] + last[i][0],
      course: courseNames[ci], group: groups[ci], progress: (i * 37 + 18) % 97 + 3,
      pay: pay[i % pay.length], status: i === 7 || i === 19 ? 'blocked' : 'active',
      seen: seen[i % seen.length], coins: (i * 113) % 900 + 40, phone: '+998 9' + (i % 10) + ' ' + (100 + i * 7) + ' ' + (10 + i) + ' ' + (20 + i)
    };
  });
  admin.payments = admin.students.slice(0, 10).map(function (s, i) {
    return { name: s.name, initials: s.initials, course: s.course, amount: [450000, 600000, 380000, 520000][i % 4],
             date: (i + 1) + '-noyabr', status: s.pay === 'debt' ? 'debt' : (i % 5 === 3 ? 'partial' : 'paid') };
  });

  var teacher = {
    user: { name: 'Aziza Tursunova', first: 'Aziza', role: 'Öqituvçi', initials: 'AT' },
    // teacher.views.teacher_dashboard context
    stats: { total_students: 68, groups: 5, pending_homeworks: 9, pending_speakings: 3,
             avg_test_score: 79.6, pass_rate: 86, avg_check_hours: 5.2, week_change: 14 },
    // StudyGroup: name, profession, start_time, end_time, days_mask, room, color, students
    groups: [
      { id: 1, name: 'FE-24', course: 'Frontend (React)', students: 14, progress: 62, days: [1, 3, 5], time: '09:00 – 10:30', room: '204-xona', status: 'active', att: 93 },
      { id: 2, name: 'FE-27', course: 'Frontend (React)', students: 12, progress: 28, days: [2, 4, 6], time: '11:00 – 12:30', room: '204-xona', status: 'active', att: 88 },
      { id: 3, name: 'JS-Pro', course: 'JavaScript Pro', students: 16, progress: 81, days: [1, 3, 5], time: '14:00 – 15:30', room: '301-xona', status: 'active', att: 95 },
      { id: 4, name: 'FE-Kids', course: 'Web asoslari', students: 15, progress: 45, days: [2, 4], time: '16:00 – 17:00', room: '105-xona', status: 'active', att: 84 },
      { id: 5, name: 'FE-19', course: 'Frontend (React)', students: 11, progress: 100, days: [6], time: '10:00 – 12:00', room: '204-xona', status: 'finished', att: 91 }
    ],
    today: [
      { group: 'FE-24', course: 'Frontend (React)', topic: 'React Router: dinamik marşrutlar', time: '09:00', end: '10:30', room: '204-xona', students: 14, state: 'done', marked: true },
      { group: 'JS-Pro', course: 'JavaScript Pro', topic: 'Async/Await va xatolarni uşlaş', time: '14:00', end: '15:30', room: '301-xona', students: 16, state: 'now', marked: false },
      { group: 'FE-Kids', course: 'Web asoslari', topic: 'CSS Flexbox amaliyot', time: '16:00', end: '17:00', room: '105-xona', students: 15, state: 'next', marked: false }
    ],
    queue: [
      { id: 1, student: 'Bekzod Nazarov', initials: 'BN', task: 'Todo ilova (React hooks)', group: 'FE-24', kind: 'Vazifa', ago: '40 daqiqa oldin', due: 'bugun', urgent: true },
      { id: 2, student: 'Madina Raximova', initials: 'MR', task: 'Speaking: My future job', group: 'JS-Pro', kind: 'Speaking', ago: '1 soat oldin', due: 'bugun', urgent: true },
      { id: 3, student: 'Otabek Ergashev', initials: 'OE', task: 'Fetch API bilan ob-havo ilovasi', group: 'JS-Pro', kind: 'Vazifa', ago: '3 soat oldin', due: 'ertaga', urgent: false },
      { id: 4, student: 'Sevara Olimova', initials: 'SO', task: 'Flexbox landing sahifa', group: 'FE-Kids', kind: 'Vazifa', ago: '5 soat oldin', due: 'ertaga', urgent: false },
      { id: 5, student: 'Temur Jurayev', initials: 'TJ', task: 'useReducer bilan savatça', group: 'FE-27', kind: 'Vazifa', ago: 'kecha', due: '2 kun', urgent: false },
      { id: 6, student: 'Laylo Normatova', initials: 'LN', task: 'Speaking: Describe a place', group: 'FE-24', kind: 'Speaking', ago: 'kecha', due: '2 kun', urgent: false }
    ],
    checked: [
      { id: 11, student: 'Kamola Ismoilova', initials: 'KI', task: 'Kalkulyator (DOM)', group: 'JS-Pro', kind: 'Vazifa', score: 92, ago: 'bugun 08:40' },
      { id: 12, student: 'Javohir Saidov', initials: 'JS', task: 'Props va state', group: 'FE-24', kind: 'Vazifa', score: 78, ago: 'kecha' },
      { id: 13, student: 'Zarina Abdullayeva', initials: 'ZA', task: 'Speaking: Hobbies', group: 'FE-27', kind: 'Speaking', score: 85, ago: 'kecha' }
    ],
    // activity_days (14 kun): hw + tests
    activity: { labels: ['21', '22', '23', '24', '25', '26', '27', '28', '29', '30', '31', '1', '2', '3'],
                hw: [4, 6, 3, 8, 7, 2, 1, 9, 6, 7, 10, 5, 8, 11], tests: [2, 3, 5, 4, 6, 1, 0, 5, 7, 4, 6, 3, 6, 7] },
    roster: {}
  };
  var rosterNames = first.slice(0, 16).map(function (f, i) { return { id: i + 1, name: f + ' ' + last[i], initials: f[0] + last[i][0] }; });
  teacher.groups.forEach(function (g, gi) {
    teacher.roster[g.id] = rosterNames.slice(0, g.students).map(function (s, i) {
      return { id: s.id, name: s.name, initials: s.initials, rate: 70 + ((i * 7 + gi * 3) % 30),
               status: g.id === 1 ? (i % 9 === 4 ? 'absent' : i % 11 === 6 ? 'late' : 'present') : null };
    });
  });

  return { admin: admin, teacher: teacher };
})();
