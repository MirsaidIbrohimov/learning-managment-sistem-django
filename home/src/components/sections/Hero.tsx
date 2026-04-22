import Scene3D from "@/components/Scene3D";
import { Button } from "@/components/ui/button";
import { ArrowRight, Sparkles, Play } from "lucide-react";

const getDjangoUrl = (key: string, fallback: string) => {
  const urls = (window as any).__DJANGO_URLS__;
  return urls?.[key] || fallback;
};

const Hero = () => {
  return (
    <section id="home" className="relative min-h-screen flex items-center pt-28 pb-20 overflow-hidden">
      {/* Background grid + glow */}
      <div className="absolute inset-0 grid-bg opacity-60 pointer-events-none" />
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[600px] bg-primary/20 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-0 right-0 w-[500px] h-[500px] bg-accent/20 rounded-full blur-[120px] pointer-events-none" />

      <div className="container relative z-10 grid lg:grid-cols-2 gap-12 items-center">
        {/* Text */}
        <div className="space-y-8 animate-fade-in-up">
          <div className="inline-flex items-center gap-2 glass rounded-full px-4 py-2 text-xs font-mono text-primary">
            <Sparkles className="w-3.5 h-3.5" />
            <span>2025 yilning yangi guruhlari ochildi</span>
          </div>

          <h1 className="font-display text-5xl md:text-6xl lg:text-7xl font-bold leading-[1.05] tracking-tight">
            Kelajak <span className="text-gradient">kodi</span> bilan boshlanadi
          </h1>

          <p className="text-lg text-muted-foreground max-w-xl leading-relaxed">
            ITC Academy — zamonaviy dasturlash va IT kasblariga o'rgatuvchi o'quv markaz.
            Frontend, Backend, UI/UX dizayn va sun'iy intellekt yo'nalishlarida amaliy ta'lim oling.
          </p>

          <div className="flex flex-wrap gap-4">
            <Button variant="hero" size="xl" className="group" asChild>
              <a href={getDjangoUrl('register', '/register/')}>
                Ro'yxatdan o'tish
                <ArrowRight className="w-4 h-4 transition-transform group-hover:translate-x-1" />
              </a>
            </Button>
            <Button variant="glow" size="xl" className="group" asChild>
              <a href="#courses">
                <Play className="w-4 h-4" />
                Kurslarni ko'rish
              </a>
            </Button>
          </div>

          <div className="flex flex-wrap gap-8 pt-6 border-t border-border">
            {[
              { n: "5K+", l: "Bitiruvchilar" },
              { n: "20+", l: "Kurslar" },
              { n: "95%", l: "Ish bilan ta'minlanish" },
            ].map((s) => (
              <div key={s.l}>
                <div className="font-display text-3xl font-bold text-gradient">{s.n}</div>
                <div className="text-xs text-muted-foreground mt-1 uppercase tracking-wider">{s.l}</div>
              </div>
            ))}
          </div>
        </div>

        {/* 3D Scene */}
        <div className="relative h-[500px] lg:h-[600px] animate-scale-in">
          <div className="absolute inset-0 bg-gradient-glow opacity-50" />
          <Scene3D />
          {/* Floating code badges */}
          <div className="absolute top-10 left-0 glass rounded-xl px-3 py-2 font-mono text-xs text-primary animate-float shadow-glow">
            {`< / >`} React
          </div>
          <div className="absolute bottom-20 right-0 glass rounded-xl px-3 py-2 font-mono text-xs text-accent animate-float shadow-accent-glow" style={{ animationDelay: "1.5s" }}>
            {`{ } `} Python
          </div>
          <div className="absolute top-1/2 right-4 glass rounded-xl px-3 py-2 font-mono text-xs text-foreground animate-float" style={{ animationDelay: "0.8s" }}>
            $ npm run dev
          </div>
        </div>
      </div>

      {/* Scroll indicator */}
      <div className="absolute bottom-6 left-1/2 -translate-x-1/2 hidden md:flex flex-col items-center gap-2 text-muted-foreground text-xs animate-pulse">
        <span className="font-mono">scroll</span>
        <div className="w-px h-10 bg-gradient-to-b from-primary to-transparent" />
      </div>
    </section>
  );
};

export default Hero;
