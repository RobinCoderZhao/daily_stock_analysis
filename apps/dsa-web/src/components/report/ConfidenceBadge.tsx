import type React from 'react';

interface ConfidenceBadgeProps {
  confidence: number;  // 0-100
  size?: 'sm' | 'md';
  className?: string;
}

/** Get confidence color based on score */
const getConfidenceColor = (confidence: number): string => {
  if (confidence >= 80) return '#00ff88';
  if (confidence >= 60) return '#00d4ff';
  if (confidence >= 40) return '#ffaa00';
  return '#ff4466';
};

/** Get confidence label */
const getConfidenceLabel = (confidence: number): string => {
  if (confidence >= 80) return '极高';
  if (confidence >= 60) return '较高';
  if (confidence >= 40) return '中等';
  return '较低';
};

/**
 * Confidence badge with glowing dot and score label.
 * Used in signal lists, strategy ranking tables, etc.
 */
export const ConfidenceBadge: React.FC<ConfidenceBadgeProps> = ({
  confidence,
  size = 'sm',
  className = '',
}) => {
  const color = getConfidenceColor(confidence);
  const label = getConfidenceLabel(confidence);
  const isLarge = size === 'md';

  return (
    <div
      className={`inline-flex items-center gap-1.5 rounded-full border ${className}`}
      style={{
        backgroundColor: `${color}10`,
        borderColor: `${color}30`,
        padding: isLarge ? '4px 10px' : '2px 8px',
      }}
    >
      {/* Glowing dot */}
      <span
        className="inline-block rounded-full"
        style={{
          width: isLarge ? 8 : 6,
          height: isLarge ? 8 : 6,
          backgroundColor: color,
          boxShadow: `0 0 6px ${color}80`,
        }}
      />
      {/* Score */}
      <span
        className={`font-mono font-semibold ${isLarge ? 'text-sm' : 'text-xs'}`}
        style={{ color }}
      >
        {confidence.toFixed(0)}
      </span>
      {/* Label */}
      <span
        className={`${isLarge ? 'text-xs' : 'text-[10px]'} text-muted`}
      >
        {label}
      </span>
    </div>
  );
};
