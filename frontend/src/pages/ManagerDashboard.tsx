import React, { useState, useRef } from 'react';
import { motion, AnimatePresence, useMotionValue, useTransform } from 'motion/react';
import { Search, Bell, Filter, ChevronDown, Check, X, Info, TrendingUp, Users, Wallet } from 'lucide-react';
import { cn } from '../lib/utils';
import { BentoCard } from '../components/DashboardElements';
import { MOCK_DATA } from '../constants';
import { useToast } from '../context/ToastContext';

export default function ManagerDashboard() {
  const [cards, setCards] = useState(MOCK_DATA.claims.map(c => ({
    ...c,
    employee: MOCK_DATA.employees.find(e => e.id === c.employee_id)
  })));
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const toast = useToast();

  const handleSwipe = (id: string, direction: 'left' | 'right') => {
    if (direction === 'right') {
      toast('Claim Approved Digitally', 'success');
    } else {
      toast('Sent back for clarification', 'error');
    }
    setCards(prev => prev.filter(c => c.claim_id !== id));
  };

  return (
    <div className="bg-charcoal min-h-screen">
      <main className="p-6 md:p-10 max-w-7xl mx-auto w-full relative">
        {/* Top Mega Menu Bar */}
        <header className="mb-10 flex items-center justify-between gap-6 pb-6 border-b border-white/5">
          <div className="flex items-center gap-8">
            <h1 className="text-2xl font-display font-bold">Team Lead</h1>
            <nav className="hidden lg:flex items-center gap-6">
              <MegaMenuItem label="Department" options={["Marketing", "Sales", "Engineering"]} />
              <MegaMenuItem label="Policy" options={["Travel", "Hardware", "Subscriptions"]} />
              <MegaMenuItem label="Budget" options={["Q1 2026", "Annual"]} />
            </nav>
          </div>
          
          <div className="flex items-center gap-4">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-parchment/30" />
              <input 
                type="text" 
                placeholder="Search claims..." 
                className="bg-white/5 border border-white/5 rounded-xl pl-10 pr-4 py-2 text-sm focus:border-gold/30 outline-none w-64"
              />
            </div>
            <button 
              onClick={() => setNotificationsOpen(true)}
              className="p-2.5 rounded-xl bg-white/5 border border-white/5 relative hover:bg-white/10 transition-colors"
            >
              <Bell className="w-5 h-5 text-parchment/60" />
              <span className="absolute top-2 right-2 w-2 h-2 rounded-full bg-gold border-2 border-charcoal" />
            </button>
          </div>
        </header>

        <div className="grid grid-cols-1 md:grid-cols-12 gap-8">
          {/* Tinder Swipe Section */}
          <div className="md:col-span-6 flex flex-col gap-6">
            <div className="flex items-center justify-between">
              <h3 className="text-[10px] font-display font-bold uppercase tracking-[0.2em] text-parchment/50 border-l-2 border-gold pl-3">Pending Approvals</h3>
              <p className="text-xs text-gold/60">{cards.length} claims remaining</p>
            </div>
            
            <div className="relative h-[540px] w-full flex items-center justify-center">
              <AnimatePresence>
                {cards.length > 0 ? (
                  cards.map((claim, index) => (
                    <TinderCard 
                      key={claim.claim_id} 
                      claim={claim} 
                      onSwipe={(dir) => handleSwipe(claim.claim_id, dir)}
                      isActive={index === cards.length - 1}
                    />
                  ))
                ) : (
                  <motion.div 
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    className="flex flex-col items-center gap-4 text-center p-8"
                  >
                    <div className="w-20 h-20 rounded-full bg-white/5 flex items-center justify-center text-parchment/20">
                      <Check className="w-10 h-10" />
                    </div>
                    <div>
                      <h4 className="text-lg font-display font-medium">All Caught Up</h4>
                      <p className="text-xs text-parchment/40">You've cleared the verification queue.</p>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
            
            {cards.length > 0 && (
              <div className="flex justify-center gap-4 md:hidden">
                <button 
                  onClick={() => handleSwipe(cards[cards.length-1].claim_id, 'left')}
                  className="w-14 h-14 rounded-full bg-white/5 border border-white/10 flex items-center justify-center text-parchment/40"
                >
                  <X />
                </button>
                <button 
                  onClick={() => handleSwipe(cards[cards.length-1].claim_id, 'right')}
                  className="w-14 h-14 rounded-full bg-gold/10 border border-gold/20 flex items-center justify-center text-gold"
                >
                  <Check />
                </button>
              </div>
            )}
          </div>

          {/* Team Spend Bento */}
          <div className="md:col-span-6 grid grid-cols-2 gap-4 auto-rows-[160px]">
             <BentoCard title="Team Velocity" className="col-span-2">
                <div className="flex items-center gap-6 h-full">
                  <div className="flex-1">
                    <p className="text-3xl font-display font-bold">14.2m</p>
                    <p className="text-[10px] uppercase tracking-widest text-parchment/40">Avg. Recognition Time</p>
                  </div>
                  <div className="flex-1 border-l border-white/5 pl-6">
                    <p className="text-3xl font-display font-bold text-gold">98%</p>
                    <p className="text-[10px] uppercase tracking-widest text-parchment/40">Agent Confidence</p>
                  </div>
                </div>
             </BentoCard>
             
             <BentoCard title="Headcount Cap">
                <div className="flex flex-col justify-end h-full">
                  <Users className="w-6 h-6 text-gold/40 mb-2" />
                  <p className="text-2xl font-bold">12/15</p>
                  <p className="text-[9px] uppercase tracking-tighter text-parchment/30">Active Users</p>
                </div>
             </BentoCard>

             <BentoCard title="Total Utilized">
                <div className="flex flex-col justify-end h-full">
                  <Wallet className="w-6 h-6 text-gold/40 mb-2" />
                  <p className="text-2xl font-bold">$42.8k</p>
                  <p className="text-[9px] uppercase tracking-tighter text-parchment/30">this quarter</p>
                </div>
             </BentoCard>

             <BentoCard title="Policy Alerts" className="col-span-2 row-span-1 border-gold/20 bg-gold/5">
                <div className="flex items-center gap-4 h-full">
                  <TrendingUp className="w-8 h-8 text-gold" />
                  <div>
                    <p className="text-sm font-medium">Outlier detected in Travel category.</p>
                    <p className="text-xs text-parchment/40">3 users exceeded local Uber limits this week.</p>
                  </div>
                </div>
             </BentoCard>
          </div>
        </div>

        {/* Notifications Slider */}
        <AnimatePresence>
          {notificationsOpen && (
             <>
               <motion.div 
                 initial={{ opacity: 0 }}
                 animate={{ opacity: 1 }}
                 exit={{ opacity: 0 }}
                 onClick={() => setNotificationsOpen(false)}
                 className="fixed inset-0 bg-black/40 backdrop-blur-sm z-[60]"
               />
               <motion.div 
                 initial={{ x: '100%' }}
                 animate={{ x: 0 }}
                 exit={{ x: '100%' }}
                 transition={{ type: 'spring', damping: 25 }}
                 className="fixed right-0 top-0 bottom-0 w-full max-w-md bg-charcoal border-l border-white/10 z-[70] p-8 shadow-2xl"
               >
                 <div className="flex justify-between items-center mb-8">
                   <h3 className="text-xl font-display font-medium">Notifications</h3>
                   <button onClick={() => setNotificationsOpen(false)} className="text-parchment/30 hover:text-white transition-colors">
                     <X />
                   </button>
                 </div>
                 
                 <div className="space-y-4">
                    <NotificationItem 
                      title="Policy Update" 
                      desc="EQP-001 has been adjusted to include noise-cancelling headphones." 
                      time="2h ago"
                      type="info"
                    />
                    <NotificationItem 
                      title="Priority Claim" 
                      desc="Sarah Chen submitted CLM-2024-047 (Urgent Review requested)" 
                      time="4h ago"
                      type="alert"
                    />
                    <NotificationItem 
                      title="System Maintenance" 
                      desc="Orion Engine will be offline for 10 mins at 02:00 AM UTC." 
                      time="1d ago"
                      type="info"
                    />
                 </div>
               </motion.div>
             </>
          )}
        </AnimatePresence>

        {/* Global Toast handles notifications now */}
      </main>
    </div>
  );
}

function TinderCard({ claim, onSwipe, isActive }: { claim: any, onSwipe: (dir: 'left' | 'right') => void, isActive: boolean, key?: string }) {
  const x = useMotionValue(0);
  const rotate = useTransform(x, [-200, 200], [-30, 30]);
  const opacity = useTransform(x, [-200, -100, 100, 200], [0, 1, 1, 0]);
  const background = useTransform(x, [-150, 150], ['rgba(239, 68, 68, 0.1)', 'rgba(34, 197, 94, 0.1)']);

  const handleDragEnd = (_: any, info: any) => {
    if (info.offset.x > 100) {
      onSwipe('right');
    } else if (info.offset.x < -100) {
      onSwipe('left');
    }
  };

  return (
    <motion.div
      drag={isActive ? "x" : false}
      dragConstraints={{ left: 0, right: 0 }}
      onDragEnd={handleDragEnd}
      style={{ x, rotate, opacity }}
      whileTap={{ scale: 0.98 }}
      className={cn(
        "absolute w-full h-[480px] max-w-sm rounded-[32px] p-8 glass-card cursor-grab active:cursor-grabbing select-none flex flex-col",
        !isActive && "pointer-events-none opacity-40 scale-95 -translate-y-4 shadow-none"
      )}
    >
      <motion.div style={{ backgroundColor: background }} className="absolute inset-0 rounded-[32px] pointer-events-none transition-colors" />
      
      <div className="flex justify-between items-start mb-6">
        <div>
          <h4 className="text-md font-display font-bold">{claim.employee?.name}</h4>
          <p className="text-[10px] uppercase tracking-widest text-parchment/40">{claim.employee?.department}</p>
        </div>
        <div className="flex flex-col items-end">
          <p className="text-2xl font-bold text-gold">${claim.items.reduce((acc: any, curr: any) => acc + curr.amount, 0).toFixed(2)}</p>
          <p className="text-[9px] uppercase tracking-widest text-parchment/40">{claim.claim_id}</p>
        </div>
      </div>

      <div className="flex-1 space-y-4 overflow-auto scrollbar-hide py-2">
        {claim.items.map((item: any, i: number) => (
          <div key={i} className="p-4 rounded-2xl bg-white/[0.03] border border-white/5">
            <div className="flex justify-between items-center mb-1">
              <span className="text-xs font-bold">{item.vendor}</span>
              <span className="text-xs font-medium">${item.amount}</span>
            </div>
            <p className="text-[10px] text-parchment/40 mb-2 truncate">{item.category}</p>
            <div className="flex items-center gap-2">
              <div className="flex-1 h-[2px] bg-white/5 rounded-full overflow-hidden">
                <div 
                  className={cn("h-full", item.confidence > 0.85 ? "bg-green-500" : "bg-gold")} 
                  style={{ width: `${item.confidence * 100}%` }} 
                />
              </div>
              <span className="text-[9px] font-bold text-parchment/30">{Math.round(item.confidence * 100)}% Match</span>
            </div>
          </div>
        ))}
        
        <div className="mt-4 p-4 rounded-2xl bg-gold/5 border border-gold/10">
          <p className="text-[10px] font-bold uppercase tracking-widest text-gold mb-1">AI Agent Reasoning</p>
          <p className="text-[11px] text-parchment/70 italic leading-relaxed">
            "{claim.items[0].reason || "Multiple policy triggers detected. Verification recommended."}"
          </p>
        </div>
      </div>

      <div className="pt-6 flex justify-between gap-4 mt-auto">
        <div className="flex -space-x-2">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="w-6 h-6 rounded-full bg-parchment/10 border-2 border-charcoal flex items-center justify-center text-[8px]">
              AI
            </div>
          ))}
        </div>
        <div className="flex gap-4">
           <Info className="w-5 h-5 text-parchment/20" />
           <p className="text-[10px] uppercase tracking-widest text-parchment/40 self-center">Swipe to decide</p>
        </div>
      </div>
    </motion.div>
  );
}

function MegaMenuItem({ label, options }: { label: string, options: string[] }) {
  return (
    <div className="group relative py-2">
      <button className="flex items-center gap-1.5 text-sm font-medium text-parchment/60 group-hover:text-gold transition-colors">
        {label}
        <ChevronDown className="w-3.5 h-3.5" />
      </button>
      
      <div className="absolute top-full left-0 mt-4 h-0 w-48 bg-charcoal border border-white/10 rounded-2xl opacity-0 invisible group-hover:h-auto group-hover:opacity-100 group-hover:visible transition-all duration-300 z-50 overflow-hidden shadow-2xl">
         <div className="p-4 space-y-1">
            {options.map((opt, i) => (
              <div key={i} className="px-3 py-2 rounded-lg text-xs text-parchment/60 hover:bg-white/5 hover:text-white cursor-pointer transition-colors">
                {opt}
              </div>
            ))}
         </div>
      </div>
    </div>
  );
}

function NotificationItem({ title, desc, time, type }: { title: string, desc: string, time: string, type: 'alert' | 'info' }) {
  return (
    <div className="p-4 rounded-2xl bg-white/[0.03] border border-white/5 hover:bg-white/[0.05] transition-colors cursor-pointer group">
      <div className="flex justify-between items-start mb-1">
        <h5 className="text-sm font-bold flex items-center gap-2">
          {type === 'alert' && <div className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />}
          {title}
        </h5>
        <span className="text-[10px] text-parchment/30 uppercase">{time}</span>
      </div>
      <p className="text-xs text-parchment/50 leading-relaxed line-clamp-2">{desc}</p>
    </div>
  );
}
