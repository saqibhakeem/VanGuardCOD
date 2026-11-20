import { useEffect, useRef } from "react";

interface Props {
  getMicLevels: (count: number) => number[];
  getAgentLevels: (count: number) => number[];
  isAgentActive: () => boolean;
  interruptedAt: number;
  active: boolean;
  size?: "compact" | "full";
}

interface DrawState {
  getMicLevels: (count: number) => number[];
  getAgentLevels: (count: number) => number[];
  isAgentActive: () => boolean;
  interruptedAt: number;
  active: boolean;
}

function drawBars(
  context: CanvasRenderingContext2D,
  width: number,
  baseline: number,
  levels: number[],
  color: string,
  direction: "up" | "down",
  maxHeight: number,
) {
  const gap = 2;
  const barWidth = Math.max(1, (width - gap * (levels.length - 1)) / levels.length);
  context.fillStyle = color;
  levels.forEach((raw, index) => {
    const level = Math.max(0.02, Math.min(1, raw));
    const height = level * maxHeight;
    const x = index * (barWidth + gap);
    const y = direction === "up" ? baseline - height : baseline;
    context.globalAlpha = 0.3 + level * 0.7;
    context.fillRect(x, y, barWidth, height);
  });
  context.globalAlpha = 1;
}

export function Waveform({
  getMicLevels,
  getAgentLevels,
  isAgentActive,
  interruptedAt,
  active,
  size = "compact",
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const stateRef = useRef<DrawState>({
    getMicLevels,
    getAgentLevels,
    isAgentActive,
    interruptedAt,
    active,
  });

  stateRef.current = {
    getMicLevels,
    getAgentLevels,
    isAgentActive,
    interruptedAt,
    active,
  };

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let frame = 0;

    const render = () => {
      const state = stateRef.current;
      const dpr = window.devicePixelRatio || 1;
      const width = Math.max(1, canvas.clientWidth);
      const height = Math.max(1, canvas.clientHeight);
      if (
        canvas.width !== Math.floor(width * dpr) ||
        canvas.height !== Math.floor(height * dpr)
      ) {
        canvas.width = Math.floor(width * dpr);
        canvas.height = Math.floor(height * dpr);
      }
      const context = canvas.getContext("2d");
      if (!context) return;
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      context.clearRect(0, 0, width, height);

      const middle = height / 2;
      const count = Math.max(24, Math.min(64, Math.floor(width / 6)));
      const half = middle - 8;

      context.strokeStyle = "#222634";
      context.lineWidth = 1;
      context.beginPath();
      context.moveTo(0, middle);
      context.lineTo(width, middle);
      context.stroke();

      const agentLevels = state.active
        ? state.isAgentActive()
          ? state.getAgentLevels(count)
          : new Array<number>(count).fill(0)
        : new Array<number>(count).fill(0);
      drawBars(context, width, middle - 4, agentLevels, "#06B6D4", "up", half);

      const micLevels = state.active
        ? state.getMicLevels(count)
        : new Array<number>(count).fill(0);
      drawBars(context, width, height - 4, micLevels, "#10B981", "up", half);

      if (Date.now() - state.interruptedAt < 320) {
        context.strokeStyle = "#EF4444";
        context.globalAlpha = 0.55;
        context.strokeRect(0.5, 0.5, width - 1, height - 1);
        context.globalAlpha = 1;
      }

      frame = window.requestAnimationFrame(render);
    };

    frame = window.requestAnimationFrame(render);
    return () => window.cancelAnimationFrame(frame);
  }, []);

  return (
    <div className="relative">
      <canvas
        ref={canvasRef}
        className={size === "full" ? "block h-28 w-full" : "block h-[72px] w-full"}
      />
      <span className="pointer-events-none absolute left-0 top-0 font-mono text-[9px] uppercase tracking-[0.08em] text-accent/80">
        Agent output
      </span>
      <span className="pointer-events-none absolute bottom-0 left-0 font-mono text-[9px] uppercase tracking-[0.08em] text-verified/80">
        Caller input
      </span>
    </div>
  );
}
