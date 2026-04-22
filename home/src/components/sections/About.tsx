import { Target, Users, Trophy, Lightbulb } from "lucide-react";
import { useEffect, useRef, useState } from "react";

const features = [
  { icon: Target, title: "Aniq maqsad", desc: "Har bir kurs amaliy va karyera maqsadiga yo'naltirilgan." },
  { icon: Users, title: "Tajribali ustozlar", desc: "Real loyihalarda ishlagan top mutaxassislar bilan ishlang." },
  { icon: Trophy, title: "Sertifikatlar", desc: "Xalqaro tan olinadigan diplom va sertifikatlar." },
  { icon: Lightbulb, title: "Innovatsion ta'lim", desc: "Eng so'nggi texnologiyalar va metodikalar." },
];

const About = () => {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const obs = new IntersectionObserver(
      ([e]) => e.isIntersecting && setVisible(true),
      { threshold: 0.2 }
    );
    if (ref.current) obs.observe(ref.current);
    return () => obs.disconnect();
  }, []);

  return (
    <section id="about" className="relative py-24 overflow-hidden" ref={ref}>
      <div className="absolute inset-0 grid-bg opacity-30 pointer-events-none" />

      <div className="container relative">
        <div className="max-w-3xl mb-16">
          <div className="inline-block font-mono text-xs text-primary mb-4 px-3 py-1 rounded-full bg-primary/10 border border-primary/30">
            // 01. BIZ_HAQIMIZDA
          </div>
          <h2 className="font-display text-4xl md:text-5xl font-bold leading-tight mb-6">
            IT sohasida <span className="text-gradient">yangi avlodni</span> tarbiyalaymiz
          </h2>
          <p className="text-lg text-muted-foreground leading-relaxed">
            ITC Academy — <strong className="text-foreground/90">Zomin IT Park</strong> va{" "}
            <strong className="text-foreground/90">IT shaharcha</strong> hududida joylashgan zamonaviy
            o'quv markaz. <strong className="text-foreground/90">Suyunov Husan</strong> boshchiligida
            faoliyat yuritib, yoshlarni xalqaro standartlardagi IT mutaxassislarga aylantirib kelmoqda.
            Bizning vazifamiz — har bir o'quvchini real bozor talablariga moslashtirilgan professional
            darajaga olib chiqish.
          </p>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {features.map((f, i) => (
            <div
              key={f.title}
              className={`group relative p-6 rounded-2xl glass glow-border hover:-translate-y-2 transition-all duration-500 ${
                visible ? "animate-fade-in-up" : "opacity-0"
              }`}
              style={{ animationDelay: `${i * 100}ms` }}
            >
              <div className="absolute -top-px left-1/2 -translate-x-1/2 w-1/2 h-px bg-gradient-to-r from-transparent via-primary to-transparent" />
              <div className="w-12 h-12 rounded-xl bg-gradient-primary flex items-center justify-center mb-5 shadow-glow group-hover:scale-110 transition-transform">
                <f.icon className="w-6 h-6 text-primary-foreground" />
              </div>
              <h3 className="font-display font-semibold text-lg mb-2">{f.title}</h3>
              <p className="text-sm text-muted-foreground leading-relaxed">{f.desc}</p>
              <div className="absolute top-4 right-4 font-mono text-[10px] text-muted-foreground/40">
                0{i + 1}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
};

export default About;
