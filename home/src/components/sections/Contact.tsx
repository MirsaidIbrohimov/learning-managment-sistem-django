import { Phone, Mail, MapPin, Send, MessageCircle, Instagram } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useToast } from "@/hooks/use-toast";

const Contact = () => {
  const { toast } = useToast();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    toast({
      title: "Arizangiz qabul qilindi! ✨",
      description: "Tez orada siz bilan bog'lanamiz.",
    });
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
              { icon: Phone, label: "Telefon", value: "+998 90 123 45 67", sub: "Dush-Shan, 09:00-19:00" },
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
          <form
            onSubmit={handleSubmit}
            className="lg:col-span-3 p-8 rounded-2xl bg-gradient-card border border-border shadow-card relative overflow-hidden"
          >
            <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-primary" />

            <div className="space-y-5">
              <div className="grid sm:grid-cols-2 gap-4">
                <div>
                  <label className="text-xs font-mono text-muted-foreground mb-2 block">FULL_NAME</label>
                  <Input required placeholder="Ismingiz" className="bg-background/50 border-border h-12" />
                </div>
                <div>
                  <label className="text-xs font-mono text-muted-foreground mb-2 block">PHONE</label>
                  <Input required type="tel" placeholder="+998 __ ___ __ __" className="bg-background/50 border-border h-12" />
                </div>
              </div>
              <div>
                <label className="text-xs font-mono text-muted-foreground mb-2 block">EMAIL</label>
                <Input type="email" placeholder="you@example.com" className="bg-background/50 border-border h-12" />
              </div>
              <div>
                <label className="text-xs font-mono text-muted-foreground mb-2 block">MESSAGE</label>
                <Textarea required rows={5} placeholder="Qaysi yo'nalish sizni qiziqtiradi?" className="bg-background/50 border-border resize-none" />
              </div>
              <Button type="submit" variant="hero" size="xl" className="w-full sm:w-auto">
                <Send className="w-4 h-4" />
                Yuborish
              </Button>
            </div>
          </form>
        </div>
      </div>
    </section>
  );
};

export default Contact;
