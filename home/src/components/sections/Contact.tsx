import { useState } from "react";
import { Phone, Mail, MapPin, Send, MessageCircle, Instagram, CheckCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { courses } from "@/data/courses";

const getDjangoUrl = (key: string, fallback: string) => {
  const urls = (window as any).__DJANGO_URLS__;
  return urls?.[key] || fallback;
};

const formatPhone = (value: string) => {
  const digits = value.replace(/\D/g, "").slice(0, 9);
  let formatted = "";
  if (digits.length > 0) formatted = "(" + digits.substring(0, 2);
  if (digits.length >= 2) formatted += ") ";
  if (digits.length > 2) formatted += digits.substring(2, 5);
  if (digits.length > 5) formatted += " " + digits.substring(5, 7);
  if (digits.length > 7) formatted += " " + digits.substring(7, 9);
  return formatted;
};

const Contact = () => {
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phone, setPhone] = useState("");
  const [courseInterest, setCourseInterest] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [success, setSuccess] = useState(false);

  const handlePhoneChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setPhone(formatPhone(e.target.value));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitting) return;
    setSubmitting(true);

    const arizaUrl = getDjangoUrl("ariza", "/ariza/");
    const csrfToken = (window as any).__DJANGO_URLS__?.csrf || "";

    const formData = new FormData();
    formData.append("first_name", firstName);
    formData.append("last_name", lastName);
    formData.append("phone", "+998" + phone.replace(/\D/g, ""));
    formData.append("course_interest", courseInterest);
    formData.append("csrfmiddlewaretoken", csrfToken);

    try {
      await fetch(arizaUrl, { method: "POST", body: formData });
      setSuccess(true);
    } catch {
      window.location.href = arizaUrl;
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section id="contact" className="relative py-24 overflow-hidden">
      <div className="absolute inset-0 grid-bg opacity-20 pointer-events-none" />
      <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-[700px] h-[400px] bg-accent/15 rounded-full blur-[140px] pointer-events-none" />

      <div className="container relative">
        <div className="text-center max-w-2xl mx-auto mb-14">
          <div className="inline-block font-mono text-xs text-primary mb-4 px-3 py-1 rounded-full bg-primary/10 border border-primary/30">
            // 05. ALOQA
          </div>
          <h2 className="font-display text-4xl md:text-5xl font-bold leading-tight mb-4">
            <span className="text-gradient">Bog'laning</span> — biz javob beramiz
          </h2>
          <p className="text-muted-foreground">
            Savollaringiz bormi? Konsultatsiya uchun yozing yoki to'g'ridan-to'g'ri qo'ng'iroq qiling.
          </p>
        </div>

        <div className="grid lg:grid-cols-5 gap-8">
          {/* Info cards */}
          <div className="lg:col-span-2 space-y-4">
            {[
              { icon: Phone, label: "Telefon", value: "+998 97 521 66 86", sub: "Dush-Shan, 09:00-19:00" },
              { icon: Mail, label: "Email", value: "info@itc-academy.uz", sub: "24/7 javob beramiz" },
              { icon: MapPin, label: "Manzil", value: "Zomin IT Park, IT shaharcha", sub: "Jizzax viloyati, Zomin tumani" },
            ].map((c) => (
              <div key={c.label} className="group flex items-start gap-4 p-5 rounded-2xl glass hover:border-primary/40 transition-all">
                <div className="w-12 h-12 rounded-xl bg-gradient-primary flex items-center justify-center shadow-glow shrink-0 group-hover:scale-110 transition-transform">
                  <c.icon className="w-5 h-5 text-primary-foreground" />
                </div>
                <div className="min-w-0">
                  <div className="text-xs uppercase tracking-wider text-muted-foreground font-mono">{c.label}</div>
                  <div className="font-display font-semibold text-foreground mt-0.5 truncate">{c.value}</div>
                  <div className="text-xs text-muted-foreground mt-1">{c.sub}</div>
                </div>
              </div>
            ))}

            <div className="flex gap-3 pt-2">
              {[MessageCircle, Send, Instagram].map((Icon, i) => (
                <a
                  key={i}
                  href="#"
                  className="w-12 h-12 rounded-xl glass flex items-center justify-center text-muted-foreground hover:text-primary hover:border-primary/60 hover:shadow-glow transition-all hover:-translate-y-1"
                  aria-label="Social link"
                >
                  <Icon className="w-5 h-5" />
                </a>
              ))}
            </div>
          </div>

          {/* Form */}
          {success ? (
            <div className="lg:col-span-3 p-8 rounded-2xl bg-gradient-card border border-border shadow-card relative overflow-hidden flex flex-col items-center justify-center text-center gap-4">
              <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-primary" />
              <CheckCircle className="w-16 h-16 text-green-500" />
              <h3 className="font-display text-2xl font-bold">Arizangiz qabul qilindi!</h3>
              <p className="text-muted-foreground">Tez orada siz bilan bog'lanamiz.</p>
            </div>
          ) : (
            <form
              onSubmit={handleSubmit}
              className="lg:col-span-3 p-8 rounded-2xl bg-gradient-card border border-border shadow-card relative overflow-hidden"
            >
              <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-primary" />

              <div className="space-y-5">
                <div className="grid sm:grid-cols-2 gap-4">
                  <div>
                    <label className="text-xs font-mono text-muted-foreground mb-2 block">ISM</label>
                    <Input required placeholder="Ismingiz" value={firstName} onChange={(e) => setFirstName(e.target.value)} className="bg-background/50 border-border h-12" />
                  </div>
                  <div>
                    <label className="text-xs font-mono text-muted-foreground mb-2 block">FAMILIYA</label>
                    <Input required placeholder="Familiyangiz" value={lastName} onChange={(e) => setLastName(e.target.value)} className="bg-background/50 border-border h-12" />
                  </div>
                </div>
                <div>
                  <label className="text-xs font-mono text-muted-foreground mb-2 block">TELEFON</label>
                  <div className="flex items-center gap-0">
                    <span className="inline-flex items-center h-12 px-3 rounded-l-md border border-r-0 border-border bg-muted text-sm text-muted-foreground font-mono">+998</span>
                    <Input required type="tel" placeholder="(97) 521 66 86" value={phone} onChange={handlePhoneChange} className="bg-background/50 border-border h-12 rounded-l-none" />
                  </div>
                </div>
                <div>
                  <label className="text-xs font-mono text-muted-foreground mb-2 block">KURS</label>
                  <Select value={courseInterest} onValueChange={setCourseInterest}>
                    <SelectTrigger className="bg-background/50 border-border h-12">
                      <SelectValue placeholder="— Yo'nalishni tanlang —" />
                    </SelectTrigger>
                    <SelectContent>
                      {courses.map((c) => (
                        <SelectItem key={c.slug} value={c.name}>{c.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <Button type="submit" variant="hero" size="xl" className="w-full sm:w-auto" disabled={submitting}>
                  <Send className="w-4 h-4" />
                  {submitting ? "Yuborilmoqda..." : "Arizani yuborish"}
                </Button>
              </div>
            </form>
          )}
        </div>
      </div>
    </section>
  );
};

export default Contact;
