import { useEffect, useState } from "react";
import { Menu, X, Code2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/ThemeToggle";
import { cn } from "@/lib/utils";

const links = [
  { label: "Bosh sahifa", href: "#home" },
  { label: "Biz haqimizda", href: "#about" },
  { label: "Kurslar", href: "#courses" },
  { label: "Blog", href: "#blog" },
  { label: "FAQ", href: "#faq" },
  { label: "Aloqa", href: "#contact" },
];

const getDjangoUrl = (key: string, fallback: string) => {
  const urls = (window as any).__DJANGO_URLS__;
  return urls?.[key] || fallback;
};

const Navbar = () => {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 30);
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={cn(
        "fixed top-0 inset-x-0 z-50 transition-all duration-500",
        scrolled || open ? "py-3 bg-background/90 backdrop-blur-xl border-b border-border" : "py-5 bg-transparent"
      )}
    >
      <nav className="container flex items-center justify-between">
        <a href="#home" className="flex items-center gap-2.5 group">
          <div className="relative w-10 h-10 rounded-xl bg-gradient-primary flex items-center justify-center shadow-glow group-hover:scale-110 transition-transform duration-300">
            <Code2 className="w-5 h-5 text-primary-foreground" strokeWidth={2.5} />
          </div>
          <div className="font-display font-bold text-lg leading-tight">
            <div>ITC<span className="text-primary"> Academy</span></div>
            <div className="text-[10px] font-mono text-muted-foreground -mt-0.5">code.learn.build</div>
          </div>
        </a>

        <ul className="hidden lg:flex items-center gap-8">
          {links.map((l) => (
            <li key={l.href}>
              <a
                href={l.href}
                className="relative text-sm text-muted-foreground hover:text-foreground transition-colors font-medium group"
              >
                {l.label}
                <span className="absolute -bottom-1 left-0 w-0 h-0.5 bg-gradient-primary group-hover:w-full transition-all duration-300" />
              </a>
            </li>
          ))}
        </ul>

        <div className="hidden md:flex items-center gap-3">
          <ThemeToggle />
          <Button variant="ghost" size="sm" className="text-foreground hover:text-primary" asChild>
            <a href={getDjangoUrl('login', '/login/')}>Kirish</a>
          </Button>
          <Button variant="hero" size="sm" asChild>
            <a href={getDjangoUrl('register', '/register/')}>Ro'yxatdan o'tish</a>
          </Button>
        </div>

        <div className="lg:hidden flex items-center gap-2">
        <ThemeToggle />
        <button
          className="text-foreground p-2"
          onClick={() => setOpen((v) => !v)}
          aria-label="Toggle menu"
        >
          {open ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
        </button>
        </div>
      </nav>

      {/* Mobile menu */}
      {open && (
        <div className="lg:hidden container mt-4 pb-4 animate-fade-in">
          <ul className="flex flex-col gap-1 rounded-2xl p-4 bg-background/95 backdrop-blur-xl border border-border">
            {links.map((l) => (
              <li key={l.href}>
                <a
                  href={l.href}
                  onClick={() => setOpen(false)}
                  className="block py-2.5 px-3 rounded-lg text-sm text-muted-foreground hover:text-foreground hover:bg-secondary transition"
                >
                  {l.label}
                </a>
              </li>
            ))}
            <li className="flex gap-2 mt-3">
              <Button variant="ghost" size="sm" className="flex-1" asChild><a href={getDjangoUrl('login', '/login/')}>Kirish</a></Button>
              <Button variant="hero" size="sm" className="flex-1" asChild><a href={getDjangoUrl('register', '/register/')}>Ro'yxat</a></Button>
            </li>
          </ul>
        </div>
      )}
    </header>
  );
};

export default Navbar;
