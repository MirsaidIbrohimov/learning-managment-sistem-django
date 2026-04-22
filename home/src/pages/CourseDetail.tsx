import { useEffect } from "react";
import { Link, useParams } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowLeft,
  CheckCircle2,
  Clock,
  Calendar,
  Users,
  Wrench,
  Trophy,
  TrendingUp,
  GraduationCap,
  Target,
  Sparkles,
} from "lucide-react";
import Navbar from "@/components/Navbar";
import Footer from "@/components/sections/Footer";
import { Button } from "@/components/ui/button";
import { getCourse, courses } from "@/data/courses";

const fadeUp = {
  hidden: { opacity: 0, y: 30 },
  show: { opacity: 1, y: 0 },
};

const CourseDetail = () => {
  const { slug } = useParams<{ slug: string }>();
  const course = slug ? getCourse(slug) : undefined;

  useEffect(() => {
    window.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior });
    if (course) {
      document.title = `${course.name} kursi — ITC Academy | Zomin IT Park`;
      const desc = `${course.name} kursi ITC Academy'da. ${course.duration}, ${course.lang}. Oylik daromad: Junior ${course.salary.junior}, Middle ${course.salary.middle}. Zomin IT Park'da o'qing.`;
      let meta = document.querySelector('meta[name="description"]');
      if (!meta) {
        meta = document.createElement("meta");
        meta.setAttribute("name", "description");
        document.head.appendChild(meta);
      }
      meta.setAttribute("content", desc);

      // JSON-LD Course schema
      const old = document.getElementById("course-jsonld");
      if (old) old.remove();
      const script = document.createElement("script");
      script.type = "application/ld+json";
      script.id = "course-jsonld";
      script.text = JSON.stringify({
        "@context": "https://schema.org",
        "@type": "Course",
        name: `${course.name} — ITC Academy`,
        description: course.description,
        provider: {
          "@type": "EducationalOrganization",
          name: "ITC Academy",
          sameAs: "https://itc-academy.uz",
        },
        offers: {
          "@type": "Offer",
          price: course.price.replace(/\./g, ""),
          priceCurrency: "UZS",
        },
        timeRequired: course.duration,
        educationalLevel: course.level,
        teaches: course.outcomes.join(", "),
      });
      document.head.appendChild(script);
    }
    return () => {
      document.getElementById("course-jsonld")?.remove();
    };
  }, [course]);

  if (!course) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center text-center px-6">
        <h1 className="font-display text-3xl mb-4">Kurs topilmadi</h1>
        <Link to="/#courses" className="text-primary hover:underline">
          Barcha kurslarga qaytish
        </Link>
      </div>
    );
  }

  const Icon = course.icon;
  const otherCourses = courses.filter((c) => c.slug !== course.slug).slice(0, 3);

  return (
    <div className="min-h-screen bg-background text-foreground noise">
      <Navbar />

      <main className="pt-28 pb-20">
        {/* Back */}
        <div className="container mb-8">
          <Link
            to="/#courses"
            className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-primary transition-colors group"
          >
            <ArrowLeft className="w-4 h-4 transition-transform group-hover:-translate-x-1" />
            Barcha kurslarga qaytish
          </Link>
        </div>

        {/* Hero */}
        <section className="container relative overflow-hidden rounded-3xl border border-border bg-gradient-card p-8 md:p-12 mb-16">
          <div
            className="absolute inset-0 opacity-[0.07] pointer-events-none"
            style={{ background: course.gradient }}
          />
          <div className="absolute -top-20 -right-20 w-[400px] h-[400px] rounded-full blur-[120px] opacity-30"
               style={{ background: course.gradient }} />

          <div className="relative grid lg:grid-cols-3 gap-8 items-start">
            <div className="lg:col-span-2 space-y-6">
              <motion.div
                initial="hidden"
                animate="show"
                variants={fadeUp}
                transition={{ duration: 0.6 }}
                className="inline-flex items-center gap-2 font-mono text-xs px-3 py-1.5 rounded-full border border-primary/30 bg-primary/10 text-primary"
              >
                <Sparkles className="w-3.5 h-3.5" />
                {course.tagline}
              </motion.div>

              <motion.h1
                initial="hidden"
                animate="show"
                variants={fadeUp}
                transition={{ duration: 0.6, delay: 0.1 }}
                className="font-display text-4xl md:text-5xl lg:text-6xl font-bold leading-[1.05] tracking-tight"
              >
                {course.name}
              </motion.h1>

              <motion.p
                initial="hidden"
                animate="show"
                variants={fadeUp}
                transition={{ duration: 0.6, delay: 0.2 }}
                className="text-lg text-muted-foreground leading-relaxed max-w-2xl"
              >
                {course.description}
              </motion.p>

              <motion.div
                initial="hidden"
                animate="show"
                variants={fadeUp}
                transition={{ duration: 0.6, delay: 0.3 }}
                className="flex flex-wrap gap-3"
              >
                <Button variant="hero" size="lg" asChild>
                  <a href="/#contact">Ro'yxatdan o'tish</a>
                </Button>
                <Button variant="glow" size="lg" asChild>
                  <a href="/#contact">Konsultatsiya olish</a>
                </Button>
              </motion.div>
            </div>

            {/* 3D-ish icon card */}
            <motion.div
              initial={{ opacity: 0, scale: 0.85, rotate: -8 }}
              animate={{ opacity: 1, scale: 1, rotate: 0 }}
              transition={{ duration: 0.7, delay: 0.2, type: "spring" }}
              className="relative mx-auto"
            >
              <div
                className="relative w-44 h-44 md:w-56 md:h-56 rounded-3xl flex items-center justify-center shadow-elevated animate-float"
                style={{ background: course.gradient }}
              >
                <Icon className="w-20 h-20 md:w-24 md:h-24 text-primary-foreground" strokeWidth={1.5} />
                <div className="absolute -top-3 -right-3 px-3 py-1 rounded-full bg-background border border-border font-mono text-[10px] shadow-card">
                  {course.lang.split(" / ")[0]}
                </div>
                <div className="absolute -bottom-3 -left-3 px-3 py-1 rounded-full bg-background border border-border font-mono text-[10px] shadow-card">
                  {course.duration}
                </div>
              </div>
            </motion.div>
          </div>

          {/* Quick stats */}
          <div className="relative grid grid-cols-2 md:grid-cols-4 gap-4 mt-10 pt-8 border-t border-border">
            {[
              { icon: Clock, label: "Davomiyligi", value: course.duration },
              { icon: GraduationCap, label: "Daraja", value: course.level },
              { icon: Calendar, label: "Boshlanishi", value: course.startDate },
              { icon: Target, label: "Format", value: course.format },
            ].map((s, i) => (
              <motion.div
                key={s.label}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, delay: 0.3 + i * 0.08 }}
                className="flex items-start gap-3"
              >
                <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center shrink-0">
                  <s.icon className="w-4.5 h-4.5 text-primary" />
                </div>
                <div className="min-w-0">
                  <div className="text-[11px] uppercase tracking-wider text-muted-foreground font-mono">
                    {s.label}
                  </div>
                  <div className="font-display font-semibold text-sm mt-0.5">{s.value}</div>
                </div>
              </motion.div>
            ))}
          </div>
        </section>

        {/* Salary section */}
        <section className="container mb-16">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
            className="flex items-center gap-3 mb-8"
          >
            <TrendingUp className="w-6 h-6 text-primary" />
            <h2 className="font-display text-3xl md:text-4xl font-bold">
              Oylik <span className="text-gradient">daromad</span>
            </h2>
          </motion.div>

          <div className="grid md:grid-cols-3 gap-5">
            {[
              { level: "Junior", salary: course.salary.junior, desc: "0-1.5 yil tajriba", delay: 0 },
              { level: "Middle", salary: course.salary.middle, desc: "1.5-3 yil tajriba", delay: 0.1 },
              { level: "Senior", salary: course.salary.senior, desc: "3+ yil tajriba", delay: 0.2 },
            ].map((tier, i) => (
              <motion.div
                key={tier.level}
                initial={{ opacity: 0, y: 30 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ duration: 0.5, delay: tier.delay }}
                className="relative p-7 rounded-2xl bg-gradient-card border border-border hover:border-primary/40 transition-all hover:-translate-y-1 hover:shadow-elevated overflow-hidden group"
              >
                <div
                  className="absolute top-0 left-0 right-0 h-1 opacity-80"
                  style={{ background: course.gradient }}
                />
                <div className="font-mono text-[11px] text-muted-foreground tracking-wider mb-2">
                  0{i + 1} / 03
                </div>
                <div className="font-display font-bold text-2xl mb-1">{tier.level}</div>
                <div className="text-xs text-muted-foreground mb-5">{tier.desc}</div>
                <div className="font-display text-4xl font-black text-gradient">
                  {tier.salary}
                </div>
                <div className="text-xs text-muted-foreground font-mono mt-1">/ oyiga</div>
              </motion.div>
            ))}
          </div>
        </section>

        {/* Curriculum */}
        <section className="container mb-16">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
            className="mb-8"
          >
            <div className="font-mono text-xs text-primary mb-2">// DASTUR</div>
            <h2 className="font-display text-3xl md:text-4xl font-bold">
              Kursda <span className="text-gradient">nimalar o'rganasiz</span>
            </h2>
          </motion.div>

          <div className="grid md:grid-cols-2 gap-4">
            {course.modules.map((m, i) => (
              <motion.div
                key={m.title}
                initial={{ opacity: 0, x: i % 2 === 0 ? -30 : 30 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true, margin: "-50px" }}
                transition={{ duration: 0.5, delay: (i % 2) * 0.1 }}
                className="group relative p-6 rounded-2xl bg-card border border-border hover:border-primary/40 transition-all"
              >
                <div className="flex items-start gap-4 mb-4">
                  <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center shrink-0 font-mono text-sm text-primary">
                    {String(i + 1).padStart(2, "0")}
                  </div>
                  <h3 className="font-display font-semibold text-lg pt-1.5">{m.title}</h3>
                </div>
                <ul className="space-y-2 pl-1">
                  {m.topics.map((t) => (
                    <li key={t} className="flex items-start gap-2.5 text-sm text-muted-foreground">
                      <CheckCircle2 className="w-4 h-4 text-primary mt-0.5 shrink-0" />
                      {t}
                    </li>
                  ))}
                </ul>
              </motion.div>
            ))}
          </div>
        </section>

        {/* Tools */}
        <section className="container mb-16">
          <div className="flex items-center gap-3 mb-6">
            <Wrench className="w-5 h-5 text-primary" />
            <h2 className="font-display text-2xl md:text-3xl font-bold">Texnologiyalar va vositalar</h2>
          </div>
          <div className="flex flex-wrap gap-2.5">
            {course.tools.map((t, i) => (
              <motion.span
                key={t}
                initial={{ opacity: 0, scale: 0.8 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true }}
                transition={{ duration: 0.3, delay: i * 0.04 }}
                className="px-4 py-2 rounded-xl glass font-mono text-xs hover:border-primary/60 hover:text-primary transition-colors"
              >
                {t}
              </motion.span>
            ))}
          </div>
        </section>

        {/* Outcomes + Audience */}
        <section className="container mb-16 grid lg:grid-cols-2 gap-6">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
            className="p-7 rounded-2xl bg-gradient-card border border-border"
          >
            <div className="flex items-center gap-3 mb-5">
              <div className="w-10 h-10 rounded-xl bg-gradient-primary flex items-center justify-center shadow-glow">
                <Trophy className="w-5 h-5 text-primary-foreground" />
              </div>
              <h3 className="font-display font-bold text-xl">Kurs natijasi</h3>
            </div>
            <ul className="space-y-3">
              {course.outcomes.map((o) => (
                <li key={o} className="flex items-start gap-3 text-sm">
                  <CheckCircle2 className="w-4.5 h-4.5 text-primary mt-0.5 shrink-0" />
                  <span className="text-foreground/90">{o}</span>
                </li>
              ))}
            </ul>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5, delay: 0.1 }}
            className="p-7 rounded-2xl bg-gradient-card border border-border"
          >
            <div className="flex items-center gap-3 mb-5">
              <div className="w-10 h-10 rounded-xl bg-gradient-primary flex items-center justify-center shadow-glow">
                <Users className="w-5 h-5 text-primary-foreground" />
              </div>
              <h3 className="font-display font-bold text-xl">Kim uchun mos</h3>
            </div>
            <ul className="space-y-3">
              {course.audience.map((a) => (
                <li key={a} className="flex items-start gap-3 text-sm">
                  <CheckCircle2 className="w-4.5 h-4.5 text-primary mt-0.5 shrink-0" />
                  <span className="text-foreground/90">{a}</span>
                </li>
              ))}
            </ul>
            <div className="mt-6 pt-6 border-t border-border space-y-2 font-mono text-xs text-muted-foreground">
              <div><span className="text-primary">$</span> dars-jadvali: {course.schedule}</div>
              <div><span className="text-primary">$</span> joylashuv: Zomin IT Park, Suyunov Husan IT shaharcha</div>
            </div>
          </motion.div>
        </section>

        {/* CTA */}
        <section className="container mb-16">
          <div className="relative overflow-hidden rounded-3xl border border-border bg-gradient-card p-8 md:p-12 text-center">
            <div className="absolute inset-0 grid-bg opacity-30 pointer-events-none" />
            <div
              className="absolute -bottom-32 left-1/2 -translate-x-1/2 w-[600px] h-[300px] rounded-full blur-[120px] opacity-30"
              style={{ background: course.gradient }}
            />
            <div className="relative">
              <div className="font-mono text-xs text-primary mb-3">// READY_TO_START</div>
              <h2 className="font-display text-3xl md:text-4xl font-bold mb-4">
                Oylik to'lov: <span className="text-gradient">{course.price} so'm</span>
              </h2>
              <p className="text-muted-foreground max-w-xl mx-auto mb-7">
                Yangi guruhlar har oyning 1-sanasida ochiladi. Cheklangan o'rinlar — ro'yxatdan o'tib, joyingizni band qiling.
              </p>
              <div className="flex flex-wrap gap-3 justify-center">
                <Button variant="hero" size="xl" asChild>
                  <a href="/#contact">Ro'yxatdan o'tish</a>
                </Button>
                <Button variant="outlineGradient" size="xl" asChild>
                  <a href="/#contact">Bizga yozish</a>
                </Button>
              </div>
            </div>
          </div>
        </section>

        {/* Other courses */}
        <section className="container">
          <h3 className="font-display font-bold text-xl mb-6">Boshqa yo'nalishlar</h3>
          <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {otherCourses.map((c) => {
              const CIcon = c.icon;
              return (
                <Link
                  key={c.slug}
                  to={`/courses/${c.slug}`}
                  className="group p-5 rounded-2xl bg-card border border-border hover:border-primary/40 hover:-translate-y-1 transition-all flex items-center gap-4"
                >
                  <div
                    className="w-12 h-12 rounded-xl flex items-center justify-center shrink-0 group-hover:scale-110 transition-transform"
                    style={{ background: c.gradient }}
                  >
                    <CIcon className="w-5 h-5 text-primary-foreground" />
                  </div>
                  <div className="min-w-0">
                    <div className="font-display font-semibold truncate">{c.name}</div>
                    <div className="text-xs text-muted-foreground">{c.duration} • {c.lang.split(" / ")[0]}</div>
                  </div>
                </Link>
              );
            })}
          </div>
        </section>
      </main>

      <Footer />
    </div>
  );
};

export default CourseDetail;
