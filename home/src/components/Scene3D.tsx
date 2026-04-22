import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Float, Text, RoundedBox } from "@react-three/drei";
import { Suspense, useRef, useMemo, useEffect, useState } from "react";
import { useTheme } from "next-themes";
import * as THREE from "three";

/* ---------- Theme palette ---------- */
const usePalette = () => {
  const { theme } = useTheme();
  const isLight = theme === "light";
  return {
    isLight,
    primary: isLight ? "#0891b2" : "#00D9FF",
    accent: isLight ? "#7c3aed" : "#7C3AED",
    success: isLight ? "#059669" : "#39ff88",
    text: isLight ? "#0f172a" : "#e6edff",
    windowBg: isLight ? "#f8fafc" : "#0b1020",
    titleBar: isLight ? "#e2e8f0" : "#111a33",
    outline: isLight ? "#ffffff" : "#0a0e1a",
    ambientIntensity: isLight ? 0.95 : 0.5,
  };
};

/* ---------- Mouse-driven parallax controller ---------- */
const ParallaxRig = ({ children }: { children: React.ReactNode }) => {
  const group = useRef<THREE.Group>(null);
  const mouse = useRef({ x: 0, y: 0 });
  const scroll = useRef(0);
  const { gl } = useThree();

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      const rect = gl.domElement.getBoundingClientRect();
      mouse.current.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.current.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    };
    const onTouch = (e: TouchEvent) => {
      if (!e.touches[0]) return;
      const rect = gl.domElement.getBoundingClientRect();
      mouse.current.x = ((e.touches[0].clientX - rect.left) / rect.width) * 2 - 1;
      mouse.current.y = -((e.touches[0].clientY - rect.top) / rect.height) * 2 + 1;
    };
    const onScroll = () => {
      scroll.current = window.scrollY / Math.max(1, window.innerHeight);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("touchmove", onTouch, { passive: true });
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("touchmove", onTouch);
      window.removeEventListener("scroll", onScroll);
    };
  }, [gl]);

  useFrame(() => {
    if (!group.current) return;
    const targetY = mouse.current.x * 0.45 - scroll.current * 0.3;
    const targetX = -mouse.current.y * 0.25 + scroll.current * 0.2;
    group.current.rotation.y += (targetY - group.current.rotation.y) * 0.06;
    group.current.rotation.x += (targetX - group.current.rotation.x) * 0.06;
    group.current.position.y = -scroll.current * 0.6;
  });

  return <group ref={group}>{children}</group>;
};

/* ---------- Floating terminal window ---------- */
const TerminalWindow = () => {
  const ref = useRef<THREE.Group>(null);
  const p = usePalette();
  const [lineIdx, setLineIdx] = useState(0);
  const lines = useMemo(
    () => [
      { c: p.primary, t: `> npm run hack` },
      { c: p.accent, t: `const access = "granted";` },
      { c: p.success, t: `if (skill > 9000) {` },
      { c: p.text, t: `  return "elite";` },
      { c: p.success, t: `}` },
      { c: p.primary, t: `> _` },
    ],
    [p]
  );

  useEffect(() => {
    const id = setInterval(() => setLineIdx((i) => (i + 1) % (lines.length + 2)), 900);
    return () => clearInterval(id);
  }, [lines.length]);

  useFrame((s) => {
    if (!ref.current) return;
    ref.current.rotation.z = Math.sin(s.clock.elapsedTime * 0.5) * 0.02;
  });

  return (
    <Float speed={1.2} rotationIntensity={0.15} floatIntensity={0.9}>
      <group ref={ref} position={[-1.6, 0.3, 0]}>
        <RoundedBox args={[3, 1.9, 0.12]} radius={0.08} smoothness={4}>
          <meshStandardMaterial
            color={p.windowBg}
            metalness={p.isLight ? 0.2 : 0.6}
            roughness={p.isLight ? 0.6 : 0.3}
            emissive={p.primary}
            emissiveIntensity={p.isLight ? 0.04 : 0.15}
          />
        </RoundedBox>
        <mesh position={[0, 0.78, 0.07]}>
          <planeGeometry args={[3, 0.34]} />
          <meshStandardMaterial color={p.titleBar} emissive={p.accent} emissiveIntensity={p.isLight ? 0.05 : 0.25} />
        </mesh>
        {[
          { x: -1.35, c: "#ff5f57" },
          { x: -1.2, c: "#febc2e" },
          { x: -1.05, c: "#28c840" },
        ].map((d) => (
          <mesh key={d.x} position={[d.x, 0.78, 0.09]}>
            <circleGeometry args={[0.06, 24]} />
            <meshStandardMaterial color={d.c} emissive={d.c} emissiveIntensity={1} />
          </mesh>
        ))}
        {lines.slice(0, Math.min(lineIdx, lines.length)).map((l, i) => (
          <Text
            key={i}
            position={[-1.35, 0.42 - i * 0.2, 0.08]}
            fontSize={i === 0 ? 0.13 : 0.11}
            color={l.c}
            anchorX="left"
          >
            {l.t}
          </Text>
        ))}
      </group>
    </Float>
  );
};

/* ---------- Wireframe floating cube of code ---------- */
const CodeCube = () => {
  const ref = useRef<THREE.Mesh>(null);
  const p = usePalette();
  useFrame((s) => {
    if (!ref.current) return;
    ref.current.rotation.x = s.clock.elapsedTime * 0.3;
    ref.current.rotation.y = s.clock.elapsedTime * 0.4;
  });
  return (
    <Float speed={1.6} rotationIntensity={0.3} floatIntensity={1.2}>
      <mesh ref={ref} position={[2.2, 0.4, 0]}>
        <boxGeometry args={[1.1, 1.1, 1.1]} />
        <meshStandardMaterial color={p.accent} wireframe transparent opacity={0.7} />
      </mesh>
    </Float>
  );
};

/* ---------- Brackets </> ---------- */
const CodeBrackets = () => {
  const ref = useRef<THREE.Group>(null);
  const p = usePalette();
  useFrame((s) => {
    if (!ref.current) return;
    ref.current.rotation.y = Math.sin(s.clock.elapsedTime * 0.7) * 0.5;
  });
  return (
    <Float speed={2} rotationIntensity={0.4} floatIntensity={1.4}>
      <group ref={ref} position={[2.2, -0.8, 0.5]}>
        <Text fontSize={0.9} color={p.primary} anchorX="center" outlineWidth={0.015} outlineColor={p.accent}>
          {`</>`}
        </Text>
      </group>
    </Float>
  );
};

/* ---------- Matrix rain ---------- */
const MatrixRain = () => {
  const groupRef = useRef<THREE.Group>(null);
  const p = usePalette();
  const cols = 18;
  const data = useMemo(
    () =>
      [...Array(cols)].map((_, i) => ({
        x: (i - cols / 2) * 0.38,
        speed: 0.4 + Math.random() * 0.9,
        offset: Math.random() * 6,
        useAccent: Math.random() > 0.6,
      })),
    []
  );
  useFrame((s) => {
    if (!groupRef.current) return;
    groupRef.current.children.forEach((child, i) => {
      const d = data[i];
      child.position.y = ((s.clock.elapsedTime * d.speed + d.offset) % 4.5) - 2.25;
      const mat = (child as THREE.Mesh).material as THREE.MeshBasicMaterial;
      if (mat) mat.opacity = (p.isLight ? 0.18 : 0.4) + Math.sin(s.clock.elapsedTime * 2 + i) * (p.isLight ? 0.15 : 0.3);
    });
  });
  return (
    <group ref={groupRef} position={[0, 0, -2.5]}>
      {data.map((d, i) => (
        <mesh key={i} position={[d.x, 0, 0]}>
          <planeGeometry args={[0.16, 0.26]} />
          <meshBasicMaterial color={d.useAccent ? p.accent : p.primary} transparent opacity={p.isLight ? 0.25 : 0.6} />
        </mesh>
      ))}
    </group>
  );
};

/* ---------- Orbiting binary ---------- */
const OrbitingBinary = () => {
  const groupRef = useRef<THREE.Group>(null);
  const p = usePalette();
  useFrame((s) => {
    if (!groupRef.current) return;
    groupRef.current.rotation.y = s.clock.elapsedTime * 0.2;
    groupRef.current.rotation.x = Math.sin(s.clock.elapsedTime * 0.15) * 0.3;
  });
  return (
    <group ref={groupRef}>
      {[...Array(12)].map((_, i) => {
        const angle = (i / 12) * Math.PI * 2;
        const r = 3.6;
        const isOne = i % 2 === 0;
        return (
          <Float key={i} speed={1 + i * 0.1} floatIntensity={0.4}>
            <Text
              position={[Math.cos(angle) * r, Math.sin(angle * 1.4) * 1.3, Math.sin(angle) * r]}
              fontSize={0.3}
              color={isOne ? p.primary : p.accent}
              outlineWidth={0.01}
              outlineColor={p.outline}
            >
              {isOne ? "1" : "0"}
            </Text>
          </Float>
        );
      })}
    </group>
  );
};

/* ---------- Scene root ---------- */
const Scene3D = () => {
  const p = usePalette();
  return (
    <Canvas camera={{ position: [0, 0, 6.2], fov: 50 }} dpr={[1, 2]}>
      <Suspense fallback={null}>
        <ambientLight intensity={p.ambientIntensity} />
        <directionalLight position={[5, 5, 5]} intensity={1.2} color={p.primary} />
        <pointLight position={[-5, -3, -2]} intensity={1.4} color={p.accent} />
        <pointLight position={[0, 4, 3]} intensity={0.7} color="#ffffff" />
        <ParallaxRig>
          <TerminalWindow />
          <CodeCube />
          <CodeBrackets />
          <OrbitingBinary />
          <MatrixRain />
        </ParallaxRig>
      </Suspense>
    </Canvas>
  );
};

export default Scene3D;
