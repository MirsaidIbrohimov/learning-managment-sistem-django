import { ArrowUpRight, Clock } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { courses } from "@/data/courses";

const Courses = () => {
  return (
    <section id="courses" className="relative py-24 overflow-hidden">
      <div className="absolute top-1/2 left-0 w-[400px] h-[400px] bg-accent/15 rounded-full blur-[120px] pointer-events-none" />

      <div className="container relative">
        <div className="flex flex-col md:flex-row md:items-end justify-between gap-6 mb-14">
          <div className="max-w-2xl">
            <div className="inline-block font-mono text-xs text-primary mb-4 px-3 py-1 rounded-full bg-primary/10 border border-primary/30">
              // 02. KURSLAR
            </div>
            <h2 className="font-display text-4xl md:text-5xl font-bold leading-tight">
              O'zingizga mos <span className="text-gradient">yo'nalishni</span> tanlang
            </h2>
            <p className="mt-4 text-muted-foreground max-w-xl">
              Har bir kurs alohida sahifaga ega — dasturi, narxi, oylik daromadi va to'liq ma'lumotlar.
            </p>
          </div>
          <Button variant="outlineGradient" size="lg" asChild>
            <a href="#contact">
              Konsultatsiya
              <ArrowUpRight className="w-4 h-4" />
            </a>
          </Button>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {courses.map((c, i) => (
            <Link
              to={`/courses/${c.slug}`}
              key={c.slug}
              className="group relative overflow-hidden rounded-2xl bg-gradient-card border border-border hover:border-primary/40 transition-all duration-500 hover:-translate-y-2 hover:shadow-elevated block"
              style={{ animationDelay: `${i * 80}ms` }}
            >
              <div className="absolute top-0 left-0 right-0 h-1 opacity-80" style={{ background: c.gradient }} />

              <div className="p-7">
                <div className="flex items-start justify-between mb-6">
                  <div
                    className="w-14 h-14 rounded-xl flex items-center justify-center shadow-glow group-hover:rotate-6 group-hover:scale-110 transition-transform duration-500"
                    style={{ background: c.gradient }}
                  >
                    <c.icon className="w-7 h-7 text-primary-foreground" strokeWidth={2} />
                  </div>
                  <span className="font-mono text-[10px] text-muted-foreground/60 mt-2">0{i + 1}/0{courses.length}</span>
                </div>

                <h3 className="font-display font-bold text-xl mb-2 group-hover:text-primary transition-colors">
                  {c.name}
                </h3>
                <p className="font-mono text-xs text-muted-foreground mb-5">{c.lang}</p>

                <div className="flex items-center gap-4 text-xs text-muted-foreground mb-6 pb-6 border-b border-border">
                  <span className="flex items-center gap-1.5">
                    <Clock className="w-3.5 h-3.5" /> {c.duration}
                  </span>
                  <span>•</span>
                  <span>{c.level}</span>
                </div>

                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-xs text-muted-foreground">Oylik to'lov</div>
                    <div className="font-display text-lg font-bold text-foreground">
                      {c.price} <span className="text-xs text-muted-foreground font-normal">so'm</span>
                    </div>
                  </div>
                  <span className="w-10 h-10 rounded-full bg-secondary border border-border flex items-center justify-center text-muted-foreground group-hover:bg-primary group-hover:text-primary-foreground group-hover:border-primary transition-all duration-300 group-hover:rotate-45">
                    <ArrowUpRight className="w-4 h-4" />
                  </span>
                </div>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </section>
  );
};

export default Courses;
