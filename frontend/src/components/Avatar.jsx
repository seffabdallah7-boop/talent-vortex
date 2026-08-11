const COLORS = [
  "bg-blue-500", "bg-emerald-500", "bg-violet-500", "bg-orange-500",
  "bg-pink-500", "bg-cyan-500", "bg-amber-500", "bg-rose-500", "bg-teal-500",
];

function hashIdx(s) {
  let h = 0;
  for (let i = 0; i < (s || "").length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
  return h;
}

export function Avatar({ name = "", src, size = 40, className = "", onClick, testId }) {
  const initials =
    (name || "").trim().split(/\s+/).slice(0, 2).map((w) => w[0]?.toUpperCase()).join("") || "?";
  const color = COLORS[hashIdx(name) % COLORS.length];
  const style = { width: size, height: size };
  const clickable = onClick ? "cursor-pointer hover:ring-2 hover:ring-primary/50 transition-shadow" : "";
  const common = `shrink-0 rounded-full overflow-hidden flex items-center justify-center ${clickable} ${className}`;
  const validSrc = typeof src === "string" && /^(https?:\/\/|data:image\/)/.test(src);

  if (validSrc) {
    return (
      <img
        src={src}
        alt={name}
        style={style}
        onClick={onClick}
        data-testid={testId}
        className={`object-cover ${common}`}
      />
    );
  }
  return (
    <div style={style} onClick={onClick} data-testid={testId} className={`${color} text-white font-semibold ${common}`}>
      <span style={{ fontSize: size * 0.4 }}>{initials}</span>
    </div>
  );
}

export default Avatar;
