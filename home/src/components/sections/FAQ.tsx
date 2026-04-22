import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";

const faqs = [
  { q: "Kurslar qanday boshlanadi va qaysi formatda o'tadi?", a: "Kurslarimiz oflayn (Toshkent shahridagi o'quv markazda) va onlayn formatlarda olib boriladi. Har bir guruh haftada 3 marta, 2 soatdan dars o'tadi. Yangi guruhlar har oyning boshida ochiladi." },
  { q: "Boshlang'ich darajadagi o'quvchilar uchun mos keladimi?", a: "Albatta! Bizning ko'plab kurslarimiz nol darajadan boshlanadi. Frontend, UI/UX va Data Science kabi yo'nalishlar uchun maxsus 'noldan' modullar mavjud. Tajribali ustozlar har bir o'quvchi bilan individual ishlaydi." },
  { q: "Kurs tugagandan so'ng sertifikat beriladimi?", a: "Ha, har bir kursning yakuniy imtihonidan o'tgan o'quvchilarga ITC Academy nomidan rasmiy sertifikat beriladi. Bundan tashqari, eng yaxshi bitiruvchilarga sherik kompaniyalardan tavsiyanomalar ham taqdim etiladi." },
  { q: "Ish bilan ta'minlash xizmati bormi?", a: "Ha. Bizda Career Center bo'limi mavjud bo'lib, u CV tayyorlash, intervyuga tayyorgarlik va sherik kompaniyalarga (EPAM, Workly, IT Park rezidentlari) yo'naltirish bilan shug'ullanadi. Bitiruvchilarimizning 95%+ ish bilan ta'minlanadi." },
  { q: "To'lovni qaysi tartibda amalga oshirsam bo'ladi?", a: "To'lovni naqd, plastik karta, bank o'tkazmasi yoki muddatli to'lov (rassrochka) orqali amalga oshirish mumkin. Bundan tashqari, A'lo darajadagi o'quvchilarga 50% gacha grant chegirmalari beriladi." },
  { q: "Bir vaqtda bir nechta kursni o'rganish mumkinmi?", a: "Texnik jihatdan mumkin, lekin biz bunga maslahat bermaymiz — har bir kurs jiddiy vaqt va e'tibor talab qiladi. Avval bitta yo'nalishda mustahkam asosiy bilim olish samaraliroqdir." },
];

const FAQ = () => {
  return (
    <section id="faq" className="relative py-24 overflow-hidden">
      <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-primary/10 rounded-full blur-[120px] pointer-events-none" />

      <div className="container relative">
        <div className="grid lg:grid-cols-5 gap-12">
          {/* Left intro */}
          <div className="lg:col-span-2 lg:sticky lg:top-32 self-start">
            <div className="inline-block font-mono text-xs text-primary mb-4 px-3 py-1 rounded-full bg-primary/10 border border-primary/30">
              // 04. FAQ
            </div>
            <h2 className="font-display text-4xl md:text-5xl font-bold leading-tight mb-6">
              Tez-tez <br /> <span className="text-gradient">so'raladigan</span> <br /> savollar
            </h2>
            <p className="text-muted-foreground leading-relaxed mb-6">
              Sizni qiziqtirgan barcha savollar bo'yicha bizning team bilan bog'laning yoki quyidagi javoblarni o'qing.
            </p>
            <div className="font-mono text-xs text-muted-foreground space-y-1.5">
              <div><span className="text-primary">$</span> read --faq</div>
              <div><span className="text-primary">›</span> 06 question(s) found</div>
            </div>
          </div>

          {/* Right accordion */}
          <div className="lg:col-span-3">
            <Accordion type="single" collapsible className="space-y-3">
              {faqs.map((f, i) => (
                <AccordionItem
                  key={i}
                  value={`item-${i}`}
                  className="border border-border rounded-xl bg-card/50 px-5 hover:border-primary/40 transition-colors data-[state=open]:border-primary/60 data-[state=open]:bg-card data-[state=open]:shadow-glow"
                >
                  <AccordionTrigger className="text-left font-display font-semibold text-base hover:no-underline py-5">
                    <span className="flex items-start gap-4">
                      <span className="font-mono text-xs text-primary mt-1">0{i + 1}</span>
                      {f.q}
                    </span>
                  </AccordionTrigger>
                  <AccordionContent className="text-muted-foreground leading-relaxed pl-9">
                    {f.a}
                  </AccordionContent>
                </AccordionItem>
              ))}
            </Accordion>
          </div>
        </div>
      </div>
    </section>
  );
};

export default FAQ;
