import { Code, Server, Palette, Smartphone, Brain, Database, type LucideIcon } from "lucide-react";

export interface Course {
  slug: string;
  icon: LucideIcon;
  name: string;
  tagline: string;
  lang: string;
  level: string;
  duration: string;
  gradient: string;
  price: string;
  salary: { junior: string; middle: string; senior: string };
  description: string;
  modules: { title: string; topics: string[] }[];
  tools: string[];
  outcomes: string[];
  audience: string[];
  schedule: string;
  format: string;
  startDate: string;
}

export const courses: Course[] = [
  {
    slug: "frontend",
    icon: Code,
    name: "Frontend Development",
    tagline: "Zamonaviy veb interfeyslar yarating",
    lang: "JavaScript / React / TypeScript",
    level: "Boshlang'ich → Pro",
    duration: "8 oy",
    gradient: "linear-gradient(135deg, hsl(var(--primary)), hsl(var(--primary-glow)))",
    price: "1.200.000",
    salary: { junior: "$500–800", middle: "$1.200–2.000", senior: "$2.500–4.500" },
    description:
      "Frontend Development kursida siz nol darajadan boshlab zamonaviy veb-saytlar va veb-ilovalar yaratishni o'rganasiz. HTML, CSS, JavaScript asoslaridan to React, TypeScript va Next.js gacha to'liq yo'l.",
    modules: [
      { title: "1-modul: Veb asoslari", topics: ["HTML5 semantik teglar", "CSS3 va Flexbox/Grid", "Responsive dizayn", "Tailwind CSS"] },
      { title: "2-modul: JavaScript", topics: ["ES6+ sintaksisi", "DOM manipulyatsiyasi", "Async / await, Promise", "Fetch API"] },
      { title: "3-modul: TypeScript", topics: ["Tiplar tizimi", "Interfeyslar va Generics", "Type guards", "Loyihada qo'llash"] },
      { title: "4-modul: React", topics: ["Komponentlar va Props", "Hooks (useState, useEffect)", "React Router", "Context API"] },
      { title: "5-modul: Holat boshqaruvi", topics: ["Redux Toolkit", "Zustand", "TanStack Query", "Form boshqaruvi"] },
      { title: "6-modul: Pro daraja", topics: ["Next.js 14 (App Router)", "SSR / SSG / ISR", "Performance optimizatsiya", "Diplom loyihasi"] },
    ],
    tools: ["VS Code", "Git / GitHub", "Figma", "Vite", "React", "TypeScript", "Tailwind", "Next.js"],
    outcomes: [
      "Mustaqil ravishda zamonaviy SPA va veb-saytlar yarata olasiz",
      "Real loyihalardan iborat portfolio (5+ loyiha)",
      "GitHub profilingiz tayyor — ish berish uchun",
      "Texnik intervyularga to'liq tayyor",
    ],
    audience: ["Dasturlashni 0 dan boshlamoqchilar", "Dizaynerlar — kod tomoniga o'tmoqchilar", "Backend dasturchilar — full-stack bo'lmoqchilar"],
    schedule: "Haftada 3 marta, har biri 2 soat",
    format: "Oflayn (Zomin IT Park) / Onlayn (Zoom)",
    startDate: "Har oyning 1-sanasi",
  },
  {
    slug: "backend",
    icon: Server,
    name: "Backend Development",
    tagline: "Server, ma'lumotlar bazasi va API",
    lang: "Node.js / Python / Go",
    level: "O'rta darajadan",
    duration: "9 oy",
    gradient: "linear-gradient(135deg, hsl(var(--accent)), hsl(var(--accent-glow)))",
    price: "1.400.000",
    salary: { junior: "$600–1.000", middle: "$1.500–2.500", senior: "$3.000–5.500" },
    description:
      "Backend Development kursida siz katta yuklamaga bardosh beradigan, xavfsiz va kengaytiriladigan server tizimlari yaratishni o'rganasiz. Node.js, REST/GraphQL API, PostgreSQL va mikroservislar.",
    modules: [
      { title: "1-modul: Asoslar", topics: ["Linux komandalar", "HTTP / REST", "Git workflow", "JavaScript chuqur"] },
      { title: "2-modul: Node.js", topics: ["Express.js", "Middleware", "Autentifikatsiya (JWT)", "Fayl yuklash"] },
      { title: "3-modul: Ma'lumotlar bazalari", topics: ["PostgreSQL", "Prisma ORM", "MongoDB", "Redis kesh"] },
      { title: "4-modul: API arxitektura", topics: ["REST best practices", "GraphQL", "WebSockets", "Hujjatlash (Swagger)"] },
      { title: "5-modul: DevOps", topics: ["Docker", "CI/CD", "AWS / VPS deploy", "Monitoring"] },
      { title: "6-modul: Mikroservislar", topics: ["Mikroservis arxitektura", "Message queue (RabbitMQ)", "Test yozish", "Diplom loyihasi"] },
    ],
    tools: ["Node.js", "Express", "PostgreSQL", "Prisma", "Docker", "Postman", "AWS", "Git"],
    outcomes: [
      "Production-ready REST/GraphQL API yarata olasiz",
      "Ma'lumotlar bazasini to'g'ri loyihalashtirasiz",
      "Docker bilan deploy qila olasiz",
      "Real bozor talablariga javob beradigan backend dasturchi",
    ],
    audience: ["Frontend dasturchilar — full-stack bo'lmoqchilar", "Algoritm yaxshi biluvchilar", "Server logikasiga qiziquvchilar"],
    schedule: "Haftada 3 marta, har biri 2.5 soat",
    format: "Oflayn (Zomin IT Park) / Onlayn",
    startDate: "Har oyning 1-sanasi",
  },
  {
    slug: "ui-ux",
    icon: Palette,
    name: "UI / UX Design",
    tagline: "Mahsulot dizayni va foydalanuvchi tajribasi",
    lang: "Figma / Adobe XD",
    level: "Boshlang'ich",
    duration: "6 oy",
    gradient: "linear-gradient(135deg, hsl(var(--accent)), hsl(var(--primary)))",
    price: "1.000.000",
    salary: { junior: "$400–700", middle: "$1.000–1.800", senior: "$2.200–4.000" },
    description:
      "UI/UX Design kursida siz foydalanuvchi tadqiqotidan boshlab, mukammal interfeys dizaynigacha bo'lgan to'liq mahsulot dizayni jarayonini o'rganasiz. Figma, dizayn tizimlari va prototiplash.",
    modules: [
      { title: "1-modul: Dizayn nazariyasi", topics: ["Rang nazariyasi", "Tipografika", "Kompozitsiya", "Gestalt prinsiplari"] },
      { title: "2-modul: UX tadqiqot", topics: ["Foydalanuvchi intervyu", "Persona", "User journey", "Wireframing"] },
      { title: "3-modul: Figma Pro", topics: ["Auto-layout", "Komponentlar va variantlar", "Plug-inlar", "Design tokens"] },
      { title: "4-modul: UI dizayn", topics: ["Mobil ilovalar UI", "Veb-sayt UI", "Mikrointeraksiyalar", "Animatsiyalar"] },
      { title: "5-modul: Dizayn tizimlari", topics: ["Atomik dizayn", "Komponent kutubxonasi", "Hujjatlash", "Dasturchi bilan ishlash"] },
      { title: "6-modul: Portfolio", topics: ["Case study yozish", "Behance / Dribbble", "Mijoz bilan ishlash", "Diplom loyihasi"] },
    ],
    tools: ["Figma", "Adobe XD", "Photoshop", "Illustrator", "Principle", "Notion", "Miro", "Spline"],
    outcomes: [
      "Mahsulot dizaynini boshidan oxirigacha yaratasiz",
      "8+ case study bo'lgan kuchli portfolio",
      "Behance/Dribbble profilingiz tayyor",
      "Freelance va kompaniyalarda ishlash imkoniyati",
    ],
    audience: ["Ijodkor odamlar — dizaynga qiziquvchilar", "Marketologlar — UX tomoniga o'tmoqchilar", "Frontend dasturchilar — dizayn bilimini chuqurlashtiruvchilar"],
    schedule: "Haftada 3 marta, har biri 2 soat",
    format: "Oflayn (Zomin IT Park) / Onlayn",
    startDate: "Har oyning 1-sanasi",
  },
  {
    slug: "mobile",
    icon: Smartphone,
    name: "Mobile Development",
    tagline: "iOS va Android ilovalar yaratish",
    lang: "Flutter / React Native",
    level: "O'rta darajadan",
    duration: "8 oy",
    gradient: "linear-gradient(135deg, hsl(var(--primary)), hsl(var(--accent)))",
    price: "1.300.000",
    salary: { junior: "$500–900", middle: "$1.300–2.200", senior: "$2.800–5.000" },
    description:
      "Mobile Development kursida siz bir xil kod bazasidan iOS va Android ilovalar yaratishni o'rganasiz. Flutter (Dart) va React Native asosida real ilovalar yarating.",
    modules: [
      { title: "1-modul: Asoslar", topics: ["Dart tili", "OOP", "Async dasturlash", "Mobil dizayn prinsiplari"] },
      { title: "2-modul: Flutter UI", topics: ["Widgetlar", "Layout tizimi", "Animatsiyalar", "Custom paint"] },
      { title: "3-modul: Holat boshqaruvi", topics: ["Provider", "Riverpod", "BLoC", "GetX"] },
      { title: "4-modul: Backend integratsiya", topics: ["REST API", "Firebase", "Push notifications", "Lokal saqlash"] },
      { title: "5-modul: Native imkoniyatlar", topics: ["Kamera, GPS", "Sensorlar", "Native moduli", "Platforma kanallari"] },
      { title: "6-modul: Nashr qilish", topics: ["Play Market", "App Store", "Performance", "Diplom loyihasi"] },
    ],
    tools: ["Flutter", "Dart", "Android Studio", "Xcode", "Firebase", "Figma", "Git", "Postman"],
    outcomes: [
      "iOS va Android ilovalar yarata olasiz",
      "App Store / Play Market'ga ilova chiqarish",
      "3+ to'liq mobil ilova portfolioda",
      "Mobile dasturchi sifatida ish topish",
    ],
    audience: ["Frontend dasturchilar", "Mobil ilovalarga qiziquvchilar", "Startap g'oyasi bor tadbirkorlar"],
    schedule: "Haftada 3 marta, har biri 2.5 soat",
    format: "Oflayn (Zomin IT Park) / Onlayn",
    startDate: "Har oyning 1-sanasi",
  },
  {
    slug: "ai-ml",
    icon: Brain,
    name: "AI & Machine Learning",
    tagline: "Sun'iy intellekt va Machine Learning",
    lang: "Python / TensorFlow",
    level: "Yuqori daraja",
    duration: "10 oy",
    gradient: "linear-gradient(135deg, hsl(var(--accent-glow)), hsl(var(--primary-glow)))",
    price: "1.800.000",
    salary: { junior: "$800–1.300", middle: "$2.000–3.500", senior: "$4.000–7.000" },
    description:
      "AI & Machine Learning kursida siz ma'lumotlar tahlilidan boshlab chuqur o'rganish modellarini yaratishgacha bo'lgan to'liq yo'lni o'tasiz. Python, TensorFlow, PyTorch va LLM asosidagi loyihalar.",
    modules: [
      { title: "1-modul: Python va matematika", topics: ["Python Pro", "NumPy, Pandas", "Chiziqli algebra", "Statistika"] },
      { title: "2-modul: ML asoslari", topics: ["Scikit-learn", "Regressiya", "Klassifikatsiya", "Klasterlash"] },
      { title: "3-modul: Deep Learning", topics: ["Neyron tarmoqlar", "TensorFlow / Keras", "PyTorch", "GPU bilan ishlash"] },
      { title: "4-modul: Computer Vision", topics: ["CNN", "Object detection (YOLO)", "Image segmentation", "OpenCV"] },
      { title: "5-modul: NLP & LLM", topics: ["Transformerlar", "Hugging Face", "Fine-tuning", "RAG tizimlari"] },
      { title: "6-modul: MLOps", topics: ["Model deploy", "Docker, FastAPI", "Monitoring", "Diplom loyihasi"] },
    ],
    tools: ["Python", "Jupyter", "TensorFlow", "PyTorch", "Hugging Face", "scikit-learn", "Docker", "FastAPI"],
    outcomes: [
      "ML modellarini yaratish va deploy qilish",
      "Computer Vision va NLP loyihalari",
      "LLM bilan ishlay olish (RAG, fine-tuning)",
      "AI Engineer / Data Scientist sifatida ishlash",
    ],
    audience: ["Matematika va statistikani yaxshi biluvchilar", "Backend dasturchilar — AI'ga o'tmoqchilar", "Tadqiqotchilar"],
    schedule: "Haftada 3 marta, har biri 3 soat",
    format: "Oflayn (Zomin IT Park) / Onlayn",
    startDate: "Har oyning 1-sanasi",
  },
  {
    slug: "data-science",
    icon: Database,
    name: "Data Science",
    tagline: "Ma'lumotlar bilan qaror qabul qilish",
    lang: "Python / SQL / Pandas",
    level: "Boshlang'ich → Pro",
    duration: "9 oy",
    gradient: "linear-gradient(135deg, hsl(var(--primary-glow)), hsl(var(--accent)))",
    price: "1.500.000",
    salary: { junior: "$700–1.100", middle: "$1.700–2.800", senior: "$3.200–5.500" },
    description:
      "Data Science kursida siz katta hajmdagi ma'lumotlardan biznesga foyda keltiradigan tushunchalar olishni o'rganasiz. Python, SQL, vizualizatsiya va prediktiv tahlil.",
    modules: [
      { title: "1-modul: Asoslar", topics: ["Python", "SQL", "Statistika", "Excel Pro"] },
      { title: "2-modul: Ma'lumot tahlili", topics: ["Pandas", "NumPy", "Ma'lumot tozalash", "EDA"] },
      { title: "3-modul: Vizualizatsiya", topics: ["Matplotlib, Seaborn", "Plotly", "Tableau", "Power BI"] },
      { title: "4-modul: ML for Data", topics: ["Regressiya", "Klassifikatsiya", "Time series", "A/B test"] },
      { title: "5-modul: Big Data", topics: ["PySpark", "Airflow", "Data warehouse", "Cloud (BigQuery)"] },
      { title: "6-modul: Mahsulot", topics: ["Dashboard yaratish", "Hisobotlar", "Stakeholder bilan ishlash", "Diplom loyihasi"] },
    ],
    tools: ["Python", "SQL", "Pandas", "Tableau", "Power BI", "Jupyter", "Airflow", "BigQuery"],
    outcomes: [
      "Real biznes ma'lumotlari bilan ishlash",
      "Dashboard va hisobotlar yaratish",
      "Prediktiv modellar qurish",
      "Data Analyst / Data Scientist sifatida ishga joylashish",
    ],
    audience: ["Iqtisodchilar, marketologlar", "Backend dasturchilar — analitikaga o'tuvchilar", "Tadqiqotchilar"],
    schedule: "Haftada 3 marta, har biri 2.5 soat",
    format: "Oflayn (Zomin IT Park) / Onlayn",
    startDate: "Har oyning 1-sanasi",
  },
];

export const getCourse = (slug: string) => courses.find((c) => c.slug === slug);
