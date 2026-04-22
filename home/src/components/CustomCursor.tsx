import { useEffect, useRef, useState } from "react";

/**
 * Smooth, animated coding-themed cursor.
 * - Inner dot follows the pointer instantly
 * - Outer ring eases toward target (lerp)
 * - Grows + shows a `</>` glyph when hovering interactive elements
 * - Hidden on touch devices and on screens < 1024px
 */
const CustomCursor = () => {
  const dotRef = useRef<HTMLDivElement>(null);
  const ringRef = useRef<HTMLDivElement>(null);
  const target = useRef({ x: 0, y: 0 });
  const ring = useRef({ x: 0, y: 0 });
  const [active, setActive] = useState(false);
  const [enabled, setEnabled] = useState(false);
  const [hovering, setHovering] = useState(false);

  useEffect(() => {
    const fine = window.matchMedia("(pointer: fine)").matches && window.innerWidth >= 1024;
    setEnabled(fine);
    if (!fine) return;

    const onMove = (e: MouseEvent) => {
      target.current.x = e.clientX;
      target.current.y = e.clientY;
      if (dotRef.current) {
        dotRef.current.style.transform = `translate3d(${e.clientX}px, ${e.clientY}px, 0) translate(-50%, -50%)`;
      }
      setActive(true);

      // Detect interactive element under cursor
      const el = document.elementFromPoint(e.clientX, e.clientY) as HTMLElement | null;
      const interactive = !!el?.closest('a, button, [role="button"], input, textarea, select, [data-cursor="hover"]');
      setHovering(interactive);
    };

    const onLeave = () => setActive(false);
    const onDown = () => ringRef.current?.classList.add("cursor-ring--down");
    const onUp = () => ringRef.current?.classList.remove("cursor-ring--down");

    let raf = 0;
    const loop = () => {
      ring.current.x += (target.current.x - ring.current.x) * 0.18;
      ring.current.y += (target.current.y - ring.current.y) * 0.18;
      if (ringRef.current) {
        ringRef.current.style.transform = `translate3d(${ring.current.x}px, ${ring.current.y}px, 0) translate(-50%, -50%)`;
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseleave", onLeave);
    window.addEventListener("mousedown", onDown);
    window.addEventListener("mouseup", onUp);

    document.body.classList.add("has-custom-cursor");

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseleave", onLeave);
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("mouseup", onUp);
      document.body.classList.remove("has-custom-cursor");
    };
  }, []);

  if (!enabled) return null;

  return (
    <>
      <div
        ref={dotRef}
        className={`pointer-events-none fixed left-0 top-0 z-[9999] w-2 h-2 rounded-full bg-primary mix-blend-difference transition-opacity duration-300 ${
          active ? "opacity-100" : "opacity-0"
        }`}
      />
      <div
        ref={ringRef}
        className={`cursor-ring pointer-events-none fixed left-0 top-0 z-[9998] flex items-center justify-center rounded-full border border-primary/60 backdrop-blur-sm transition-[width,height,background,border-color] duration-300 ease-out ${
          active ? "opacity-100" : "opacity-0"
        } ${hovering ? "w-14 h-14 bg-primary/10 border-primary" : "w-9 h-9 bg-transparent"}`}
      >
        <span
          className={`font-mono text-[10px] text-primary transition-opacity duration-200 ${
            hovering ? "opacity-100" : "opacity-0"
          }`}
        >
          {`</>`}
        </span>
      </div>
    </>
  );
};

export default CustomCursor;
