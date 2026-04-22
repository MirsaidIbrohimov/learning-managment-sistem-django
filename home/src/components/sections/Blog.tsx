import { Calendar, ArrowRight } from "lucide-react";

const posts = [
  {
    tag: "FRONTEND",
    title: "React 19 yangiliklari: Server Components va kelajak",
    excerpt: "React'ning eng yangi versiyasi qanday o'zgarishlar olib keldi va dasturchilar uchun nimalar muhim?",
    date: "12 Apr, 2026",
    read: "5 daqiqa",
    accent: "linear-gradient(135deg, hsl(var(--primary) / 0.25), hsl(var(--primary-glow) / 0.18))",
  },
  {
    tag: "AI",
    title: "Sun'iy intellekt o'rganishni qayerdan boshlash kerak?",
    excerpt: "Boshlang'ichlar uchun AI va Machine Learning dunyosiga to'liq qo'llanma — vositalar, kurslar va resurslar.",
    date: "08 Apr, 2026",
    read: "8 daqiqa",
    accent: "linear-gradient(135deg, hsl(var(--accent) / 0.25), hsl(var(--accent-glow) / 0.18))",
  },
  {
    tag: "CAREER",
    title: "Junior dasturchi sifatida birinchi ishni topish yo'llari",
    excerpt: "Portfolio yaratish, intervyularga tayyorgarlik va halol maslahatlar — bizning bitiruvchilarimiz tajribasi.",
    date: "01 Apr, 2026",
    read: "6 daqiqa",
    accent: "linear-gradient(135deg, hsl(var(--accent) / 0.25), hsl(var(--primary) / 0.18))",
  },
];

const Blog = () => {
  return (
    <section id="blog" className="relative py-24 overflow-hidden">
      <div className="container relative">
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-14">
          <div className="max-w-2xl">
            <div className="inline-block font-mono text-xs text-primary mb-4 px-3 py-1 rounded-full bg-primary/10 border border-primary/30">
              // 03. BLOG
            </div>
            <h2 className="font-display text-4xl md:text-5xl font-bold leading-tight">
              IT dunyosidan <span className="text-gradient">so'nggi yangiliklar</span>
            </h2>
          </div>
        </div>

        <div className="grid md:grid-cols-3 gap-6">
          {posts.map((p, i) => (
            <article
              key={p.title}
              className="group relative rounded-2xl overflow-hidden bg-card border border-border hover:border-primary/40 transition-all duration-500 hover:-translate-y-2"
            >
              {/* Visual header */}
              <div className="relative h-44 overflow-hidden" style={{ background: p.accent }}>
                <div className="absolute inset-0 grid-bg opacity-30" />
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="font-display font-black text-7xl text-foreground/15 group-hover:scale-110 transition-transform duration-700">
                    0{i + 1}
                  </span>
                </div>
                <div className="absolute top-4 left-4 font-mono text-[10px] tracking-widest px-2.5 py-1 rounded-full bg-background/70 backdrop-blur border border-border">
                  {p.tag}
                </div>
              </div>

              <div className="p-6">
                <div className="flex items-center gap-3 text-xs text-muted-foreground mb-3">
                  <span className="flex items-center gap-1.5"><Calendar className="w-3 h-3" /> {p.date}</span>
                  <span>•</span>
                  <span>{p.read}</span>
                </div>
                <h3 className="font-display font-bold text-lg leading-snug mb-3 group-hover:text-primary transition-colors">
                  {p.title}
                </h3>
                <p className="text-sm text-muted-foreground leading-relaxed mb-5">{p.excerpt}</p>
                <a href="#" className="inline-flex items-center gap-1.5 text-sm font-medium text-primary group/link">
                  O'qishni davom ettirish
                  <ArrowRight className="w-3.5 h-3.5 transition-transform group-hover/link:translate-x-1" />
                </a>
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
};

export default Blog;
