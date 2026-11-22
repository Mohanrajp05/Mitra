const COLORS = ['#6366f1', '#f26b4f', '#0ea5a4', '#8b5cf6', '#d97706', '#16a34a', '#2563eb', '#db2777']

function colorFor(name) {
  let hash = 0
  for (let i = 0; i < name.length; i += 1) hash = (hash * 31 + name.charCodeAt(i)) >>> 0
  return COLORS[hash % COLORS.length]
}

export function initials(name = '') {
  return name
    .split(' ')
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
    .join('')
}

export default function Avatar({ name, size = 32 }) {
  return (
    <span
      className="avatar"
      title={name}
      style={{
        width: size,
        height: size,
        fontSize: Math.round(size * 0.38),
        background: colorFor(name),
      }}
    >
      {initials(name)}
    </span>
  )
}

export function AvatarStack({ names, size = 24 }) {
  return (
    <span className="avatar-stack">
      {names.map((n) => (
        <Avatar key={n} name={n} size={size} />
      ))}
    </span>
  )
}
