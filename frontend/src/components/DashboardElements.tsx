import { ReactNode } from 'react';
import { cn } from '../lib/utils';
import { motion } from 'motion/react';

export function BentoCard({
  children,
  className,
  title,
  action,
  isActive,
}: {
  children: ReactNode;
  className?: string;
  title?: string;
  action?: ReactNode;
  isActive?: boolean;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.4 }}
      className={cn(
        "glass-card rounded-2xl p-6 flex flex-col gap-4",
        isActive && "border-gold/50 shadow-[0_0_20px_rgba(247,200,115,0.2)] bg-gold/5",
        className
      )}
    >
      {title && (
        <div className="flex items-center justify-between">
          <h3 className="text-[10px] font-display font-bold uppercase tracking-[0.2em] text-parchment/50 border-l-2 border-gold pl-3">
            {title}
          </h3>
          {action}
        </div>
      )}
      <div className="flex-1">{children}</div>
    </motion.div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return (
    <motion.div
      animate={{ opacity: [0.3, 0.7, 0.3] }}
      transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
      className={cn("bg-white/10 rounded-lg", className)}
    />
  );
}

export function StatusBadge({ status, className }: { status: string, className?: string }) {
  const norm = status.toLowerCase();
  
  let baseClass = "px-2.5 py-1 rounded text-[10px] font-display font-bold uppercase tracking-wider ";
  if (norm.includes("approve") || norm.includes("compliant")) {
    baseClass += "bg-green-500/10 text-green-400 border border-green-500/20";
  } else if (norm.includes("reject") || norm.includes("violation")) {
    baseClass += "bg-red-500/10 text-red-400 border border-red-500/20";
  } else if (norm.includes("escalate") || norm.includes("pending")) {
    baseClass += "bg-gold/10 text-gold border border-gold/20";
  } else {
    baseClass += "bg-white/10 text-white/70 border border-white/20";
  }

  return (
    <span className={cn(baseClass, className)}>
      {status.replace(/_/g, ' ')}
    </span>
  );
}

export function Sidebar({ active }: { active: string }) {
  return (
    <aside className="w-64 border-r border-white/5 h-screen sticky top-0 hidden md:flex flex-col p-6 bg-charcoal">
      <div className="flex items-center gap-3 mb-12">
        <div className="w-8 h-8 rounded-lg bg-gold flex items-center justify-center text-charcoal font-bold font-display">
          O
        </div>
        <span className="font-display font-bold tracking-tight text-xl">ORION</span>
      </div>
      
      <nav className="flex-1 space-y-2">
        <SidebarLink label="Dashboard" active={active === 'dashboard'} />
        <SidebarLink label="My Claims" active={active === 'claims'} />
        <SidebarLink label="History" active={active === 'history'} />
        <SidebarLink label="Settings" active={active === 'settings'} />
      </nav>
      
      <div className="pt-6 border-t border-white/5">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-full bg-parchment/10 flex items-center justify-center text-xs font-medium">
            SC
          </div>
          <div>
            <p className="text-sm font-medium">Sarah Chen</p>
            <p className="text-[10px] text-parchment/40 uppercase tracking-tighter">Marketing</p>
          </div>
        </div>
      </div>
    </aside>
  );
}

function SidebarLink({ label, active }: { label: string; active: boolean }) {
  return (
    <div className={cn(
      "px-4 py-2.5 rounded-xl text-sm transition-all duration-200 cursor-pointer",
      active ? "bg-gold text-charcoal font-medium" : "text-parchment/60 hover:bg-white/5"
    )}>
      {label}
    </div>
  );
}
