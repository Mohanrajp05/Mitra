import { useState } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { Marquee } from "@/components/ui/marquee";
import { InteractiveHoverButton } from "@/components/ui/interactive-hover-button";
import LeftPanel from "@/components/LeftPanel";

const MailIcon = () => (
  <svg className="h-4 w-4 text-slate-400" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
    <rect x="3" y="5" width="18" height="14" rx="2" />
    <path d="m3 7 9 6 9-6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const LockIcon = () => (
  <svg className="h-4 w-4 text-slate-400" fill="currentColor" viewBox="0 0 24 24">
    <path d="M17 9V7a5 5 0 0 0-10 0v2H5v12h14V9h-2Zm-8-2a3 3 0 0 1 6 0v2H9V7Z" />
  </svg>
);

const EyeIcon = ({ off }) => (
  <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
    <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12Z" strokeLinecap="round" strokeLinejoin="round" />
    <circle cx="12" cy="12" r="3" />
    {off && <path d="M4 4l16 16" strokeLinecap="round" />}
  </svg>
);

const GoogleIcon = () => (
  <svg className="h-4 w-4" viewBox="0 0 48 48">
    <path fill="#EA4335" d="M24 9.5c3.5 0 6.6 1.2 9 3.5l6.7-6.7C35.6 2.4 30.2 0 24 0 14.6 0 6.5 5.4 2.6 13.2l7.8 6.1C12.3 13.6 17.7 9.5 24 9.5Z" />
    <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v9h12.7c-.6 3-2.3 5.5-4.8 7.2l7.5 5.8c4.4-4.1 7.1-10.1 7.1-17.5Z" />
    <path fill="#FBBC05" d="M10.4 28.7A14.5 14.5 0 0 1 9.5 24c0-1.6.3-3.2.9-4.7l-7.8-6.1A24 24 0 0 0 0 24c0 3.9.9 7.5 2.6 10.8l7.8-6.1Z" />
    <path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.5-5.8c-2.1 1.4-4.8 2.3-8.4 2.3-6.3 0-11.7-4.1-13.6-9.8l-7.8 6.1C6.5 42.6 14.6 48 24 48Z" />
  </svg>
);

const avatarTones = [
  "bg-indigo-50 text-indigo-700 border-indigo-200",
  "bg-orange-50 text-orange-700 border-orange-200",
  "bg-emerald-50 text-emerald-700 border-emerald-200",
  "bg-sky-50 text-sky-700 border-sky-200",
  "bg-rose-50 text-rose-700 border-rose-200",
  "bg-amber-50 text-amber-700 border-amber-200",
];

const getInitials = (name) =>
  name
    .split(" ")
    .map((w) => w[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

const Avatar = ({ name, tone = 0, size = 32, className }) => (
  <div
    aria-hidden="true"
    style={{ width: size, height: size, fontSize: Math.round(size * 0.36) }}
    className={cn(
      "flex shrink-0 items-center justify-center rounded-full border font-bold",
      avatarTones[tone % avatarTones.length],
      className
    )}
  >
    {getInitials(name)}
  </div>
);

const reviews = [
  {
    name: "Mohan Raj",
    role: "Head of People, Loopwise",
    body: "Mitra cut our screening time in half. It genuinely feels like a teammate.",
    tone: 0,
  },
  {
    name: "Rahul Verma",
    role: "High School Teacher",
    body: "I plan lessons in half the time now. Mitra remembers where we left off every single day.",
    tone: 3,
  },
  {
    name: "Priya Nair",
    role: "Product Designer",
    body: "Clean, fast and surprisingly thoughtful. I can't imagine my workflow without it.",
    tone: 4,
  },
  {
    name: "Arjun Mehta",
    role: "Startup Founder",
    body: "Our whole hiring pipeline got simpler overnight. Honestly the best tool we adopted this year.",
    tone: 1,
  },
  {
    name: "Sneha Iyer",
    role: "Talent Acquisition Lead",
    body: "Shortlisting used to take days. With Mitra it takes an afternoon, and the quality is better.",
    tone: 2,
  },
  {
    name: "Karan Malhotra",
    role: "Engineering Manager",
    body: "It feels like a teammate who never sleeps. My team loves it and so do I.",
    tone: 5,
  },
];

const firstRow = reviews.slice(0, reviews.length / 2);
const secondRow = reviews.slice(reviews.length / 2);

const visitors = reviews.slice(0, 5);

const ReviewCard = ({ name, role, body, tone }) => (
  <figure
    className={cn(
      "relative h-full w-60 cursor-pointer overflow-hidden rounded-xl border p-4",
      "border-slate-200 bg-slate-50/60 hover:bg-slate-100/70 transition-colors"
    )}
  >
    <div className="flex flex-row items-center gap-2.5">
      <Avatar name={name} tone={tone} size={32} />
      <div className="flex flex-col">
        <figcaption className="text-xs font-semibold text-slate-900">{name}</figcaption>
        <p className="text-[10px] font-medium text-slate-500">{role}</p>
      </div>
    </div>
    <blockquote className="mt-2 text-xs leading-relaxed text-slate-700">{body}</blockquote>
  </figure>
);

const container = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08 } },
};

const item = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { duration: 0.45, ease: "easeOut" } },
};

export default function LoginPage() {
  const [tab, setTab] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [keepSignedIn, setKeepSignedIn] = useState(true);

  const handleSubmit = (e) => {
    e.preventDefault();
    console.log({ email, password, keepSignedIn });
  };

  return (
    <div className="grid min-h-screen font-sans lg:grid-cols-2">
      <LeftPanel />
      <div className="flex items-center justify-center bg-white px-4 py-10">
      <motion.div
        className="w-full max-w-[400px]"
        variants={container}
        initial="hidden"
        animate="show"
      >
        <motion.div variants={item} className="inline-flex rounded-xl bg-slate-100/80 p-1">
          {[
            { id: "login", label: "Log in" },
            { id: "signup", label: "Sign up" },
          ].map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className="relative rounded-lg px-5 py-1.5 text-xs font-semibold"
            >
              {tab === t.id && (
                <motion.span
                  layoutId="tab-pill"
                  className="absolute inset-0 rounded-lg bg-white shadow-sm"
                  transition={{ type: "spring", stiffness: 400, damping: 32 }}
                />
              )}
              <span className={cn("relative", tab === t.id ? "text-slate-900" : "text-slate-500")}>
                {t.label}
              </span>
            </button>
          ))}
        </motion.div>

        <motion.h1 variants={item} className="mt-7 text-[26px] font-extrabold tracking-tight text-slate-900">
          Welcome back{" "}
          <motion.span
            aria-hidden="true"
            className="inline-block -m-3 cursor-pointer select-none p-3"
            animate={{ rotate: [0, 18, -8, 18, 0] }}
            transition={{ duration: 1.2, delay: 0.6 }}
            whileHover={{
              rotate: [0, -18, 18, -14, 14, -8, 8, 0],
              transition: { duration: 0.6, ease: "easeInOut" },
            }}
          >
            👋
          </motion.span>
        </motion.h1>
        <motion.p variants={item} className="mt-2 text-xs text-slate-500">
          Log in to pick up where you and Mitra left off.
        </motion.p>

        <motion.button
          variants={item}
          whileHover={{ y: -1 }}
          whileTap={{ scale: 0.98 }}
          type="button"
          className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl border border-slate-200 bg-white py-3 text-xs font-medium text-slate-800 shadow-sm transition hover:bg-slate-50"
        >
          <GoogleIcon />
          Continue with Google
        </motion.button>

        <motion.div variants={item} className="my-5 flex items-center gap-3">
          <div className="h-px flex-1 bg-slate-200" />
          <span className="text-[10px] text-slate-400">or continue with email</span>
          <div className="h-px flex-1 bg-slate-200" />
        </motion.div>

        <form onSubmit={handleSubmit}>
          <motion.div variants={item}>
            <label htmlFor="email" className="text-xs font-semibold text-slate-900">
              Email
            </label>
            <div className="mt-2 flex items-center gap-2.5 rounded-xl border border-slate-200 bg-slate-50/60 px-3 py-3 focus-within:border-indigo-500 focus-within:ring-2 focus-within:ring-indigo-100">
              <MailIcon />
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full bg-transparent text-xs text-slate-800 outline-none placeholder:text-slate-400"
                placeholder="you@company.com"
                required
              />
            </div>
          </motion.div>

          <motion.div variants={item} className="mt-5">
            <div className="flex items-center justify-between">
              <label htmlFor="password" className="text-xs font-semibold text-slate-900">
                Password
              </label>
              <a href="#" className="text-[10px] font-semibold text-orange-600 hover:underline">
                Forgot password?
              </a>
            </div>
            <div className="mt-2 flex items-center gap-2.5 rounded-xl border border-slate-200 bg-slate-50/60 px-3 py-3 focus-within:border-indigo-500 focus-within:ring-2 focus-within:ring-indigo-100">
              <LockIcon />
              <input
                id="password"
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full bg-transparent text-xs text-slate-800 outline-none"
                required
              />
              <button
                type="button"
                onClick={() => setShowPassword((s) => !s)}
                aria-label={showPassword ? "Hide password" : "Show password"}
                className="text-slate-400 hover:text-slate-600"
              >
                <EyeIcon off={showPassword} />
              </button>
            </div>
          </motion.div>

          <motion.label variants={item} className="mt-4 flex cursor-pointer items-center gap-2 text-xs text-slate-700">
            <input
              type="checkbox"
              checked={keepSignedIn}
              onChange={(e) => setKeepSignedIn(e.target.checked)}
              className="h-3.5 w-3.5 rounded accent-indigo-600"
            />
            Keep me signed in for 30 days
          </motion.label>

          <motion.div variants={item}>
            <InteractiveHoverButton
              type="submit"
              className="mt-5 w-full rounded-xl py-3 text-xs shadow-lg shadow-sky-200/60"
            >
              Log in
            </InteractiveHoverButton>
          </motion.div>
        </form>

        <motion.p variants={item} className="mt-5 text-center text-[11px] text-slate-500">
          New to Mitra?{" "}
          <a href="#" className="font-semibold text-orange-600 hover:underline">
            Create a free account
          </a>
        </motion.p>

        <motion.div variants={item} className="mt-7">
          <div className="flex items-center justify-center gap-3">
            <div className="flex -space-x-2">
              {visitors.map((v) => (
                <Avatar
                  key={v.name}
                  name={v.name}
                  tone={v.tone}
                  size={28}
                  className="border-2 border-white ring-1 ring-slate-200"
                />
              ))}
            </div>
            <p className="text-left text-[11px] text-slate-500">
              <span className="font-semibold text-slate-700">1000+</span> people visited Mitra
            </p>
          </div>

          <div className="relative mt-4 flex w-full flex-col items-center justify-center overflow-hidden">
            <Marquee pauseOnHover className="[--duration:25s]">
              {firstRow.map((review) => (
                <ReviewCard key={review.name} {...review} />
              ))}
            </Marquee>
            <Marquee reverse pauseOnHover className="[--duration:25s]">
              {secondRow.map((review) => (
                <ReviewCard key={review.name} {...review} />
              ))}
            </Marquee>
            <div className="pointer-events-none absolute inset-y-0 left-0 w-1/4 bg-gradient-to-r from-white" />
            <div className="pointer-events-none absolute inset-y-0 right-0 w-1/4 bg-gradient-to-l from-white" />
          </div>
        </motion.div>

        <motion.p variants={item} className="mt-6 text-center text-[10px] text-slate-400">
          By continuing you agree to our{" "}
          <a href="#" className="underline">Terms</a> and{" "}
          <a href="#" className="underline">Privacy Policy</a>.
        </motion.p>
      </motion.div>
      </div>
    </div>
  );
}
