import type React from 'react';
import { useState, useEffect, useRef } from 'react';
import type { CompositeScore } from '../../types/analysis';

interface CompositeScoreGaugeProps {
  compositeScore: CompositeScore;
  className?: string;
}

/** Get color based on composite score total */
const getScoreColor = (total: number): string => {
  if (total >= 85) return '#00ff88';   // green - strong buy
  if (total >= 70) return '#00d4ff';   // cyan - buy
  if (total >= 55) return '#a855f7';   // purple - watch
  if (total >= 40) return '#ffaa00';   // orange - neutral
  return '#ff4466';                     // red - avoid
};

/** Get label badge background */
const getLabelBg = (label: string): string => {
  const map: Record<string, string> = {
    '强烈推荐': 'rgba(0, 255, 136, 0.15)',
    '推荐买入': 'rgba(0, 212, 255, 0.15)',
    '可以关注': 'rgba(168, 85, 247, 0.15)',
    '中性观望': 'rgba(255, 170, 0, 0.15)',
    '建议回避': 'rgba(255, 68, 102, 0.15)',
  };
  return map[label] || 'rgba(255, 255, 255, 0.05)';
};

/**
 * Composite Score Gauge - terminal-style ring gauge with factor breakdown bars.
 */
export const CompositeScoreGauge: React.FC<CompositeScoreGaugeProps> = ({
  compositeScore,
  className = '',
}) => {
  const { total, label, technical, fundamental, moneyFlow, market, confidence } = compositeScore;

  // Animated score counting
  const [animatedScore, setAnimatedScore] = useState(0);
  const [displayScore, setDisplayScore] = useState(0);
  const animRef = useRef<number | null>(null);
  const prevRef = useRef(0);

  useEffect(() => {
    const start = prevRef.current;
    const end = total;
    const duration = 800;
    const startTime = performance.now();

    const animate = (now: number) => {
      const elapsed = now - startTime;
      const progress = Math.min(elapsed / duration, 1);
      const easeOut = 1 - Math.pow(1 - progress, 3);
      const current = start + (end - start) * easeOut;
      setAnimatedScore(current);
      setDisplayScore(Math.round(current));
      if (progress < 1) {
        animRef.current = requestAnimationFrame(animate);
      } else {
        prevRef.current = end;
      }
    };
    animRef.current = requestAnimationFrame(animate);
    return () => { if (animRef.current) cancelAnimationFrame(animRef.current); };
  }, [total]);

  const width = 140;
  const strokeW = 10;
  const radius = (width - strokeW) / 2;
  const circumference = 2 * Math.PI * radius;
  const arcLength = circumference * 0.75;
  const progress = (animatedScore / 100) * arcLength;
  const color = getScoreColor(animatedScore);
  const glowColor = `${color}66`;

  // Factor breakdown bars
  const factors = [
    { name: '技术面', value: technical, max: 40, color: '#00d4ff' },
    { name: '基本面', value: fundamental, max: 30, color: '#a855f7' },
    { name: '资金流', value: moneyFlow, max: 20, color: '#ffaa00' },
    { name: '大盘', value: market, max: 10, color: '#00ff88' },
  ];

  return (
    <div className={`flex flex-col items-center ${className}`}>
      {/* Label badge */}
      <span
        className="text-xs font-semibold px-3 py-1 rounded-full mb-2"
        style={{ backgroundColor: getLabelBg(label), color }}
      >
        {label}
      </span>

      {/* Ring gauge */}
      <div className="relative" style={{ width, height: width }}>
        <svg
          className="overflow-visible"
          width={width}
          height={width}
          style={{ filter: `drop-shadow(0 0 10px ${glowColor})` }}
        >
          <defs>
            <linearGradient id="comp-grad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor={color} stopOpacity="0.6" />
              <stop offset="100%" stopColor={color} stopOpacity="1" />
            </linearGradient>
            <filter id="comp-glow">
              <feGaussianBlur stdDeviation="3" result="blur" />
              <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </defs>

          {/* Background track */}
          <circle
            cx={width / 2} cy={width / 2} r={radius}
            fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth={strokeW}
            strokeLinecap="round"
            strokeDasharray={`${arcLength} ${circumference}`}
            transform={`rotate(135 ${width / 2} ${width / 2})`}
          />
          {/* Glow */}
          <circle
            cx={width / 2} cy={width / 2} r={radius}
            fill="none" stroke={color} strokeWidth={strokeW + 6}
            strokeLinecap="round"
            strokeDasharray={`${progress} ${circumference}`}
            transform={`rotate(135 ${width / 2} ${width / 2})`}
            opacity="0.25" filter="url(#comp-glow)"
          />
          {/* Progress arc */}
          <circle
            cx={width / 2} cy={width / 2} r={radius}
            fill="none" stroke="url(#comp-grad)" strokeWidth={strokeW}
            strokeLinecap="round"
            strokeDasharray={`${progress} ${circumference}`}
            transform={`rotate(135 ${width / 2} ${width / 2})`}
          />
        </svg>

        {/* Center score */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span
            className="font-bold text-4xl text-white"
            style={{ textShadow: `0 0 20px ${glowColor}` }}
          >
            {displayScore}
          </span>
          <span className="text-[10px] text-muted mt-0.5">COMPOSITE</span>
        </div>
      </div>

      {/* Factor breakdown bars */}
      <div className="w-full mt-3 space-y-1.5 px-1">
        {factors.map((f) => (
          <div key={f.name} className="flex items-center gap-2 text-xs">
            <span className="text-muted w-12 flex-shrink-0 text-right">{f.name}</span>
            <div className="flex-1 h-1.5 rounded-full bg-white/5 overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-700"
                style={{
                  width: `${(f.value / f.max) * 100}%`,
                  backgroundColor: f.color,
                  boxShadow: `0 0 6px ${f.color}66`,
                }}
              />
            </div>
            <span className="font-mono text-white w-8 text-right">
              {f.value.toFixed(0)}<span className="text-muted">/{f.max}</span>
            </span>
          </div>
        ))}
      </div>

      {/* Confidence indicator */}
      <div className="mt-2 flex items-center gap-1.5 text-xs">
        <span className="text-muted">置信度</span>
        <span className="font-mono font-semibold" style={{ color }}>
          {confidence.toFixed(0)}%
        </span>
      </div>
    </div>
  );
};
