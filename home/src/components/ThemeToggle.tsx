import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

export const ThemeToggle = () => {
  const { theme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  const isDark = theme !== "light";

  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label="Mavzuni almashtirish"
      onClick={() => setTheme(isDark ? "light" : "dark")}
      className="relative rounded-full border border-border hover:border-primary/50 hover:text-primary transition-all"
    >
      {mounted && (
        <>
          <Sun
            className={`w-[18px] h-[18px] transition-all duration-500 ${
              isDark ? "rotate-90 scale-0 opacity-0" : "rotate-0 scale-100 opacity-100"
            }`}
          />
          <Moon
            className={`absolute w-[18px] h-[18px] transition-all duration-500 ${
              isDark ? "rotate-0 scale-100 opacity-100" : "-rotate-90 scale-0 opacity-0"
            }`}
          />
        </>
      )}
    </Button>
  );
};
