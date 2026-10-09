import { Code2, Send, Instagram, MessageCircle, Youtube } from "lucide-react";

const Footer = () => {
  return (
    <footer className="relative border-t border-border pt-16 pb-8 overflow-hidden">
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-1/3 h-px bg-gradient-to-r from-transparent via-primary to-transparent" />

      <div className="container">
        <div className="grid md:grid-cols-4 gap-10 mb-12">
          <div className="md:col-span-2">
            <a href="#home" className="flex items-center gap-2.5 mb-5">
              <div className="w-10 h-10 rounded-xl bg-gradient-primary flex items-center justify-center shadow-glow">
                <Code2 className="w-5 h-5 text-primary-foreground" strokeWidth={2.5} />
              </div>
              <div className="font-display font-bold text-lg">
                ITC<span className="text-primary"> Academy</span>
              </div>
            </a>
            <p className="text-sm text-muted-foreground leading-relaxed max-w-md mb-6">
              IT va dasturlash sohasida zamonaviy ta'lim. O'zbekistondagi eng innovatsion
              o'quv markaz — kelajak texnologiyalarini bugundan o'rganing.
            </p>
            <div className="flex gap-3">
              {[
                { Icon: MessageCircle, href: "https://t.me/husanbek_coder", label: "Telegram" },
                { Icon: Send, href: "https://t.me/husanbek_coder", label: "Telegram channel" },
                { Icon: Instagram, href: "https://instagram.com/itc.academy", label: "Instagram" },
                { Icon: Youtube, href: "https://youtube.com/@it_creative", label: "YouTube" },
              ].map((s) => (
                <a key={s.label} href={s.href} target="_blank" rel="noopener noreferrer" aria-label={s.label} className="w-9 h-9 rounded-lg bg-secondary border border-border flex items-center justify-center text-muted-foreground hover:text-primary hover:border-primary transition-colors">
                  <s.Icon className="w-4 h-4" />
                </a>
              ))}
            </div>
          </div>

          <div>
            <h4 className="font-display font-semibold mb-4">Navigatsiya</h4>
            <ul className="space-y-2.5 text-sm text-muted-foreground">
              {["Bosh sahifa", "Biz haqimizda", "Kurslar", "Blog", "FAQ"].map((l) => (
                <li key={l}>
                  <a href="#" className="hover:text-primary transition-colors">{l}</a>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <h4 className="font-display font-semibold mb-4">Kurslar</h4>
            <ul className="space-y-2.5 text-sm text-muted-foreground">
              {["Frontend", "Backend", "UI/UX Design", "Mobile Dev", "AI / ML"].map((l) => (
                <li key={l}>
                  <a href="#" className="hover:text-primary transition-colors">{l}</a>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="pt-8 border-t border-border flex flex-col md:flex-row justify-between gap-4 items-center">
          <p className="text-xs text-muted-foreground font-mono">
            © {new Date().getFullYear()} ITC Academy. All rights reserved.
          </p>
          <p className="text-xs text-muted-foreground font-mono">
            Made with <span className="text-primary">{`</>`}</span> in Toshkent
          </p>
        </div>
      </div>
    </footer>
  );
};

export default Footer;
