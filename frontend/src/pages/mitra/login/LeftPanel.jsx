import { motion } from "framer-motion";
import { cn } from "./lib/utils";
import girl from "./assets/girl.png";
import mascot from "./assets/Doll.png";
import logo from "./assets/logo.png";

const Svg = ({ children, className }) => (
  <svg
    className={cn("h-3 w-3", className)}
    fill="none"
    stroke="currentColor"
    strokeWidth="2.2"
    strokeLinecap="round"
    strokeLinejoin="round"
    viewBox="0 0 24 24"
  >
    {children}
  </svg>
);

const icons = {
  design: (
    <Svg>
      <path d="M6 6l12 12M18 6 6 18" />
    </Svg>
  ),
  chart: (
    <Svg>
      <path d="M5 20V10M12 20V4M19 20v-7" />
    </Svg>
  ),
  code: (
    <Svg>
      <path d="m8 7-5 5 5 5M16 7l5 5-5 5" />
    </Svg>
  ),
  search: (
    <Svg>
      <circle cx="11" cy="11" r="6" />
      <path d="m20 20-4.2-4.2" />
    </Svg>
  ),
  target: (
    <Svg>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="3" />
    </Svg>
  ),
};

const VerifiedBadge = () => (
  <span className="flex h-3 w-3 items-center justify-center rounded-full bg-emerald-500">
    <svg className="h-2 w-2 text-white" fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
      <path d="m5 12 5 5 9-10" />
    </svg>
  </span>
);

const CheckDot = () => (
  <span className="flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full bg-indigo-600">
    <svg className="h-2 w-2 text-white" fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" viewBox="0 0 24 24">
      <path d="m5 12 5 5 9-10" />
    </svg>
  </span>
);

const Chip = ({ label, color, icon, verified, style, delay = 0 }) => (
  <motion.div
    style={style}
    animate={{ y: [0, -4, 0] }}
    transition={{ duration: 3.6, repeat: Infinity, ease: "easeInOut", delay }}
    className="absolute flex items-center gap-1.5 whitespace-nowrap rounded-full bg-white py-1 pl-1 pr-2.5 text-[10px] font-semibold text-slate-800 shadow-[0_4px_14px_rgba(99,102,241,0.16)]"
  >
    <span className={cn("flex h-5 w-5 items-center justify-center rounded-full text-white", color)}>
      {icons[icon]}
    </span>
    {label}
    {verified && <VerifiedBadge />}
  </motion.div>
);

const points = [
  "AI agents will make your work easier",
  "You review every AI suggestion before it goes out",
  "Built for recruiters and small HR teams",
];

export default function LeftPanel() {
  return (
    <aside
      className="relative hidden flex-col justify-between self-start overflow-hidden p-10 lg:sticky lg:top-0 lg:flex lg:h-screen"
      style={{
        background:
          "linear-gradient(160deg, #e9e8fd 0%, #f3eefa 55%, #fee5db 100%)",
      }}
    >
      <img
        src={logo}
        alt="Mitra"
        className="h-14 w-14 self-start rounded-full object-cover shadow-md shadow-indigo-300/40"
      />

      <div className="flex flex-1 items-center justify-center py-6">
        <div className="relative h-[250px] w-[360px]">
          <div className="absolute left-[62px] top-[2px] h-[236px] w-[236px] rounded-full border border-dashed border-indigo-200" />
          <div className="absolute left-[108px] top-[50px] h-[124px] w-[124px] rounded-full bg-white/70" />

          <img
            src={girl}
            alt="Smiling Mitra user holding a phone"
            className="absolute"
            style={{ left: 120, top: 50, width: 120, height: 214 }}
          />

          <Chip label="Product Designer" color="bg-pink-500" icon="design" verified style={{ left: 8, top: 5 }} />
          <Chip label="Data Analyst" color="bg-emerald-500" icon="chart" verified style={{ left: 258, top: 25 }} delay={0.6} />
          <Chip label="Frontend Engineer" color="bg-sky-500" icon="code" verified style={{ left: 239, top: 87 }} delay={1.2} />
          <Chip label="UX Researcher" color="bg-amber-500" icon="search" style={{ left: 7, top: 100 }} delay={0.9} />
          <Chip label="Product Manager" color="bg-violet-500" icon="target" style={{ left: 16, top: 178 }} delay={0.3} />

          <div
            className="absolute rounded-xl bg-white px-3 py-2 text-[10px] leading-snug text-slate-600 shadow-[0_4px_14px_rgba(99,102,241,0.16)]"
            style={{ left: 211, top: 133, width: 135 }}
          >
            Mitra helps you find roles based on your requirements
          </div>

          <motion.img
            src={mascot}
            alt=""
            className="absolute"
            style={{ left: 303, top: 183, width: 41, height: 41 }}
            animate={{ y: [0, -5, 0] }}
            transition={{ duration: 2.8, repeat: Infinity, ease: "easeInOut" }}
          />
        </div>
      </div>

      <div>
        <h2 className="text-[28px] font-extrabold leading-[1.15] tracking-tight text-slate-900">
          Hiring feels lighter
          <br />
          with a <span className="text-orange-500">friend</span> by your side.
        </h2>
        <p className="mt-4 max-w-sm text-xs leading-relaxed text-slate-500">
          Mitra reads resumes, finds great matches, drafts thoughtful emails and
          books interviews — so you can focus on people.
        </p>
        <ul className="mt-5 space-y-2">
          {points.map((p) => (
            <li key={p} className="flex items-center gap-2 text-[11px] text-slate-700">
              <CheckDot />
              {p}
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}
