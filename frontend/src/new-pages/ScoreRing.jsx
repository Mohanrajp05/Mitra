export function scoreColor(score) {
  if (score >= 85) return 'var(--success)'
  if (score >= 70) return 'var(--primary)'
  return 'var(--amber)'
}

export default function ScoreRing({ score, size = 44, stroke = 4 }) {
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference * (1 - Math.max(0, Math.min(100, score)) / 100)

  return (
    <span className="ring" style={{ width: size, height: size }} role="img" aria-label={`Match score ${score} out of 100`}>
      <svg width={size} height={size}>
        <circle className="ring-track" cx={size / 2} cy={size / 2} r={radius} fill="none" strokeWidth={stroke} />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={scoreColor(score)}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
      </svg>
      <span className="ring-value" style={{ fontSize: Math.round(size * 0.3) }}>
        {score}
      </span>
    </span>
  )
}
