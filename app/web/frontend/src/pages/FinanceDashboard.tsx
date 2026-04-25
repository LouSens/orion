import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Shield, ChevronLeft, ChevronRight, BarChart3, Database, Search, FileDown, Plus, ExternalLink, Filter, ArrowUpRight } from 'lucide-react';
import { cn } from '../lib/utils';
import { BentoCard, StatusBadge } from '../components/DashboardElements';
import { fetchLedger } from '../api/client';
import type { LedgerRecord } from '../api/types'

const POLICIES = [
  // ── HARD ─────────────────────────────────────────────────────────────────
  {
    rule_id: 'POL-004',
    title: 'Business justification required',
    text: 'All reimbursements must include a business justification of at least 10 characters.',
    enforcement: 'automatic',
    type: 'hard' as const,
  },
  {
    rule_id: 'POL-005',
    title: 'Approved category list',
    text: 'Subscriptions must fall into one of: productivity, design, engineering, ai_tools, communication, analytics, security.',
    enforcement: 'automatic',
    type: 'hard' as const,
  },
  {
    rule_id: 'POL-006',
    title: 'No duplicate active subscription',
    text: "Employees may not claim for a SaaS product the organisation already licenses and can extend a seat on.",
    enforcement: 'llm_evaluated',
    type: 'hard' as const,
  },
  {
    rule_id: 'POL-007',
    title: 'Receipt required above MYR 100',
    text: 'Any claim over MYR 100 requires a receipt or invoice.',
    enforcement: 'automatic',
    type: 'hard' as const,
  },
  // ── SOFT ─────────────────────────────────────────────────────────────────
  {
    rule_id: 'POL-001',
    title: 'Auto-approval threshold',
    text: 'Claims at or below MYR 500 with complete documentation may be auto-approved.',
    enforcement: 'automatic',
    type: 'soft' as const,
  },
  {
    rule_id: 'POL-002',
    title: 'Manager escalation',
    text: 'Claims above MYR 500 and at or below MYR 5000 require manager approval.',
    enforcement: 'automatic',
    type: 'soft' as const,
  },
  {
    rule_id: 'POL-003',
    title: 'Finance escalation',
    text: 'Claims above MYR 5000 require finance controller approval.',
    enforcement: 'automatic',
    type: 'soft' as const,
  },
  {
    rule_id: 'POL-008',
    title: 'Annual plan preference',
    text: 'For recurring SaaS over MYR 200/month, annual billing should be preferred when discount is meaningful.',
    enforcement: 'automatic',
    type: 'soft' as const,
  },
];

export default function FinanceDashboard() {
  const [activePolicyIdx, setActivePolicyIdx] = useState(0);
  const [expandedClaim, setExpandedClaim] = useState<string | null>(null);

  // Fallback mock data shaped like LedgerRecord for when the API is unreachable
  const [ledgerRecords, setLedgerRecords] = useState<LedgerRecord[]>([
    {
      claim_id: 'CLM-2024-047',
      employee_id: 'sarah_chen_mktg',
      vendor: 'Canva Pro',
      product: 'Subscription',
      amount_myr: 38.97,
      decision: 'escalate_manager',
      recorded_at: '2026-04-20T10:05:00Z',
      notification_sent_to: ['sarah_chen_mktg', 'james_torres_mktg'],
    },
    {
      claim_id: 'CLM-2024-048',
      employee_id: 'raj_kumar_bd',
      vendor: 'Zoom',
      product: 'Pro',
      amount_myr: 101.98,
      decision: 'auto_approve',
      recorded_at: '2026-04-18T10:00:00Z',
      notification_sent_to: ['raj_kumar_bd'],
    },
  ]);

  // Fetch real ledger data from the backend API on mount
  useEffect(() => {
    fetchLedger()
      .then((data) => {
        if (data.records && data.records.length > 0) {
          setLedgerRecords(data.records);
        }
      })
      .catch((err) => {
        console.warn('Ledger API unavailable, using fallback mock data:', err.message);
      });
  }, []);

  const nextPolicy = () => setActivePolicyIdx(prev => (prev + 1) % POLICIES.length);
  const prevPolicy = () => setActivePolicyIdx(prev => (prev - 1 + POLICIES.length) % POLICIES.length);

  return (
    <div className="bg-charcoal min-h-screen">
      <main className="p-6 md:p-10 max-w-7xl mx-auto w-full">
        {/* Header with Stats */}
        <header className="mb-12">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 mb-10">
            <div>
              <h1 className="text-3xl font-display font-bold">Finance Control</h1>
              <p className="text-parchment/40 mt-1">Audit-ready intelligent ledger management.</p>
            </div>
            <div className="flex gap-4">
              <button className="px-5 py-2.5 rounded-xl border border-white/10 hover:bg-white/5 transition-colors text-sm font-medium flex items-center gap-2">
                <FileDown className="w-4 h-4" /> Export Report
              </button>
              <button className="px-5 py-2.5 rounded-xl bg-gold text-charcoal hover:scale-[1.02] transition-transform text-sm font-bold flex items-center gap-2">
                <Plus className="w-4 h-4" /> New Rule
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
            <StatBox label="Audit Coverage" value="99.9%" sub="Verified by AI" icon={<Shield />} />
            <StatBox label="Avg. Approval" value="1.2 days" sub="-0.4 vs last month" icon={<BarChart3 />} />
            <StatBox label="Duplicate Detected" value="142" sub="Saved $12,450" icon={<Database />} />
            <StatBox label="Pending Compliance" value="12" sub="Requires attention" icon={<Shield />} />
          </div>
        </header>

        {/* Policy Carousel — 3D Infinite */}
        <section className="mb-16">
          <div className="flex items-center justify-between mb-8">
            <h2 className="text-xs font-display font-bold uppercase tracking-[0.4em] text-gold border-l-2 border-gold pl-3">Policy Engine</h2>
            <div className="flex gap-2">
              <button onClick={prevPolicy} className="p-2 rounded-full border border-white/10 hover:bg-white/5"><ChevronLeft /></button>
              <button onClick={nextPolicy} className="p-2 rounded-full border border-white/10 hover:bg-white/5"><ChevronRight /></button>
            </div>
          </div>

          <div className="relative w-full flex flex-col items-center overflow-visible">
            {/* Carousel Track: CSS Grid allows container to naturally fit the tallest card */}
            <div 
              className="grid w-full max-w-sm items-stretch relative overflow-visible"
              style={{ perspective: '1200px', transformStyle: 'preserve-3d' }}
            >
              {POLICIES.map((policy, i) => {
                let offset = i - activePolicyIdx;
                const half = POLICIES.length / 2;
                if (offset > half) offset -= POLICIES.length;
                if (offset < -half) offset += POLICIES.length;

                const isActive = offset === 0;
                const isHard = policy.type === 'hard';
                
                // Horizontal 3D Depth Positioning
                let opacity = 0;
                let rotateY = 0;
                let translateX = "0%";
                let scale = 0.6;
                let zIndex = 0;

                if (isActive) {
                  opacity = 1;
                  rotateY = 0;
                  translateX = "0%";
                  scale = 1;
                  zIndex = 10;
                } else if (offset === -1) {
                  opacity = 0.5;
                  rotateY = 40;
                  translateX = "-110%";
                  scale = 0.8;
                  zIndex = 5;
                } else if (offset === 1) {
                  opacity = 0.5;
                  rotateY = -40;
                  translateX = "110%";
                  scale = 0.8;
                  zIndex = 5;
                } else if (offset < -1) {
                  opacity = 0;
                  rotateY = 40;
                  translateX = "-150%";
                  scale = 0.6;
                  zIndex = 0;
                } else if (offset > 1) {
                  opacity = 0;
                  rotateY = -40;
                  translateX = "150%";
                  scale = 0.6;
                  zIndex = 0;
                }

                return (
                  <div
                    key={policy.rule_id}
                    style={{ 
                      gridArea: '1 / 1',
                      transform: `translateX(${translateX}) scale(${scale}) rotateY(${rotateY}deg)`,
                      opacity,
                      zIndex
                    }}
                    className={cn(
                      "w-full rounded-[32px] p-8 glass-card border-2 transition-all duration-200 ease-out flex flex-col",
                      isActive ? "pointer-events-auto" : "pointer-events-none",
                      isActive && isHard
                        ? "border-gold shadow-[0_0_40px_rgba(247,200,115,0.18)]"
                        : isActive
                        ? "border-gold/50"
                        : "border-white/5"
                    )}
                  >
                  {/* Header */}
                  <div className="flex items-start justify-between gap-3 mb-5">
                    <div className="flex items-center gap-3">
                      <div className={cn(
                        "w-10 h-10 rounded-xl flex items-center justify-center shrink-0",
                        isHard ? "bg-gold/15 text-gold" : "bg-gold/10 text-gold/70"
                      )}>
                        <Shield className="w-5 h-5" />
                      </div>
                      <div>
                        <span className="text-[10px] font-bold text-parchment/40 uppercase tracking-widest">{policy.rule_id}</span>
                        <h4 className="text-sm font-display font-bold leading-tight">{policy.title}</h4>
                      </div>
                    </div>
                    <span className={cn(
                      "shrink-0 mt-0.5 px-2 py-0.5 rounded-full text-[8px] font-bold uppercase tracking-widest",
                      isHard
                        ? "bg-red-500/20 text-red-400"
                        : "bg-sky-500/15 text-sky-400"
                    )}>
                      {isHard ? 'Hard' : 'Soft'}
                    </span>
                  </div>

                  {/* Description */}
                  <p className="text-sm text-parchment/60 leading-relaxed min-h-[72px]">
                    {policy.text}
                  </p>

                  {/* Footer */}
                  <div className="mt-auto flex justify-between items-center bg-white/5 -mx-8 -mb-8 px-8 py-5 rounded-b-[32px]">
                    <span className={cn(
                      "text-[10px] uppercase font-bold tracking-widest",
                      isHard ? "text-red-400/70" : "text-sky-400/70"
                    )}>
                      {policy.enforcement === 'llm_evaluated' ? 'LLM Evaluated' : 'Automatic'}
                    </span>
                    <button className="text-xs text-gold font-bold flex items-center gap-1">
                      Edit Rule <ArrowUpRight className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              );
            })}
            </div>
            
            {/* Dots */}
            <div className="mt-8 flex gap-2">
              {POLICIES.map((_, i) => (
                <div 
                  key={i} 
                  className={cn(
                    "w-2 h-2 rounded-full transition-colors duration-200", 
                    activePolicyIdx === i ? "bg-gold" : "bg-white/20"
                  )} 
                />
              ))}
            </div>
          </div>
        </section>

        {/* Audit Trail & Analytics */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          {/* Audit List */}
          <div className="lg:col-span-8 flex flex-col gap-6">
            <div className="flex items-center justify-between pb-4 border-b border-white/5">
              <h3 className="text-[10px] font-display font-bold uppercase tracking-[0.2em] text-parchment/50 border-l-2 border-gold pl-3">Audit Trail</h3>
              <div className="flex items-center gap-4">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3 h-3 text-parchment/30" />
                  <input type="sm" placeholder="Filter audit trail..." className="bg-transparent text-xs pl-8 pr-4 py-1.5 focus:outline-none border-b border-transparent focus:border-gold/30" />
                </div>
                <Filter className="w-4 h-4 text-parchment/30 cursor-pointer" />
              </div>
            </div>

            <div className="space-y-4">
              {[...ledgerRecords]
                .sort((a, b) => new Date(b.recorded_at).getTime() - new Date(a.recorded_at).getTime())
                .map((record, i) => {

                const recordKey = record.claim_id + '-' + i;

                return (
                  <motion.div 
                    key={recordKey} 
                    initial={{ opacity: 0, x: -20 }}
                    whileInView={{ opacity: 1, x: 0 }}
                    viewport={{ once: true }}
                    transition={{ delay: i * 0.05, duration: 0.3 }}
                    className="glass-card rounded-[24px] overflow-hidden"
                  >
                    <button
                      onClick={() => setExpandedClaim(expandedClaim === recordKey ? null : recordKey)}
                      className="w-full p-6 flex items-center justify-between text-left hover:bg-white/[0.02] transition-colors"
                    >
                      <div className="flex items-center gap-6">
                        <div className="w-12 h-12 rounded-full bg-parchment/5 flex items-center justify-center text-xs font-bold ring-1 ring-white/10">
                          {record.claim_id.split('-').pop()}
                        </div>
                        <div>
                          <div className="flex items-center gap-3">
                            <h4 className="font-bold">{record.claim_id}</h4>
                            <StatusBadge status={record.decision === 'auto_approve' ? 'COMPLIANT' : record.decision === 'auto_reject' ? 'VIOLATION' : record.decision} />
                          </div>
                          <p className="text-xs text-parchment/40 mt-1">
                            {record.vendor} — {record.product} • {new Date(record.recorded_at).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}
                          </p>
                        </div>
                      </div>
                      <div className="text-right flex items-center gap-6">
                        <div>
                          <p className="text-lg font-display font-bold">RM {record.amount_myr.toFixed(2)}</p>
                          <p className="text-[9px] uppercase text-parchment/30">Total Value</p>
                        </div>
                        <div className={cn("transition-transform duration-300", expandedClaim === recordKey ? "rotate-180" : "")}>
                          <ChevronDown />
                        </div>
                      </div>
                    </button>

                    <AnimatePresence>
                      {expandedClaim === recordKey && (
                        <motion.div
                          initial={{ height: 0 }}
                          animate={{ height: 'auto' }}
                          exit={{ height: 0 }}
                          className="overflow-hidden border-t border-white/5"
                        >
                          <div className="p-8 bg-white/[0.01] grid grid-cols-1 md:grid-cols-2 gap-8">
                            <div>
                              <h5 className="text-[10px] font-bold uppercase tracking-widest text-parchment/40 mb-4">Deep Audit Analysis</h5>
                              <div className="space-y-4">
                                <div className="flex gap-4">
                                  <div className="w-6 h-6 rounded bg-gold/10 flex items-center justify-center text-[10px] font-display font-bold text-gold">
                                    A
                                  </div>
                                  <div className="flex-1">
                                    <div className="flex justify-between items-center mb-1">
                                      <p className="text-xs font-medium">{record.vendor}</p>
                                      <p className="text-xs font-bold">RM {record.amount_myr.toFixed(2)}</p>
                                    </div>
                                    <p className="text-[10px] text-parchment/50 italic leading-relaxed">
                                      Product: "{record.product}"
                                    </p>
                                    <div className="mt-2 flex items-center gap-2">
                                      <StatusBadge status={record.decision === 'auto_approve' ? 'COMPLIANT' : record.decision === 'auto_reject' ? 'VIOLATION' : record.decision} />
                                      <span className="text-[8px] text-parchment/20">Decision: {record.decision}</span>
                                    </div>
                                  </div>
                                </div>
                                {record.notification_sent_to.length > 0 && (
                                  <div className="mt-2">
                                    <p className="text-[10px] text-parchment/40">Notified: {record.notification_sent_to.join(', ')}</p>
                                  </div>
                                )}
                              </div>
                            </div>
                            <div className="bg-charcoal/40 rounded-2xl p-6 border border-white/5">
                              <h5 className="text-[10px] font-bold uppercase tracking-widest text-parchment/40 mb-4">Ledger Integrity</h5>
                              <div className="space-y-4">
                                <IntegrityLine label="Claim ID" value={record.claim_id} />
                                <IntegrityLine label="Employee" value={record.employee_id} />
                                <IntegrityLine label="AI Identity" value="Orion-Agent-V2.1" />
                                <IntegrityLine label="Recorded At" value={new Date(record.recorded_at).toLocaleString()} />
                              </div>
                              <button className="w-full mt-6 py-2 rounded-xl bg-white/5 text-xs font-bold hover:bg-white/10 transition-colors flex items-center justify-center gap-2">
                                Verify on Ledger <ExternalLink className="w-3 h-3" />
                              </button>
                            </div>
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </motion.div>
                );
              })}
            </div>
          </div>

          {/* Analytics Bento Sub-grid */}
          <div className="lg:col-span-4 flex flex-col gap-6">
            <h3 className="text-[10px] font-display font-bold uppercase tracking-[0.2em] text-parchment/50 border-l-2 border-gold pl-3">Analytics Intelligence</h3>
            <div className="grid grid-cols-1 gap-6">
              <BentoCard title="Duplicate Prevents">
                <div className="flex items-center gap-4">
                  <div className="text-3xl font-display font-bold text-green-400">$12,450</div>
                  <div className="p-1 px-2 rounded bg-green-500/10 text-green-400 text-[8px] font-bold">+12% vs LY</div>
                </div>
                <p className="text-[10px] text-parchment/40 mt-2">Recovered from phantom subscription churn.</p>
              </BentoCard>

              <BentoCard title="Policy Coverage">
                <div className="relative h-2 w-full bg-white/5 rounded-full overflow-hidden mt-2">
                  <div className="h-full bg-gold w-[82%]" />
                </div>
                <div className="flex justify-between mt-2">
                  <span className="text-[10px] text-parchment/40">82% Dynamic coverage</span>
                  <span className="text-[10px] font-bold">12 Active Rules</span>
                </div>
              </BentoCard>

              <BentoCard title="Workload Index" className="bg-white/[0.02]">
                <div className="h-20 flex items-end gap-1">
                  {[40, 70, 45, 90, 65, 30, 85].map((h, i) => (
                    <div key={i} className="flex-1 bg-gold/20 rounded-t-sm relative group cursor-help">
                      <div className="absolute bottom-0 w-full bg-gold transition-all group-hover:opacity-100" style={{ height: `${h}%`, opacity: 0.5 }} />
                    </div>
                  ))}
                </div>
                <p className="text-[10px] text-parchment/40 mt-4 text-center">Batch processing load by day</p>
              </BentoCard>
            </div>
          </div>
        </div>

        {/* Pull to refresh simulation footer */}
        <div className="mt-20 py-10 border-t border-white/5 flex flex-col items-center gap-4 opacity-30">
          <Database className="w-6 h-6 animate-pulse" />
          <p className="text-xs font-display uppercase tracking-widest text-center">Load historical records from Q4 2023</p>
        </div>
      </main>
    </div>
  );
}

function StatBox({ label, value, sub, icon }: { label: string, value: string, sub: string, icon: React.ReactNode }) {
  return (
    <div className="p-6 rounded-[24px] glass-card flex flex-col gap-1 relative overflow-hidden group">
      <div className="absolute top-[-20%] right-[-10%] w-24 h-24 bg-white/5 rounded-full blur-2xl group-hover:bg-gold/10 transition-colors" />
      <div className="text-gold mb-3 opacity-60 group-hover:opacity-100 transition-opacity">
        {icon}
      </div>
      <p className="text-[10px] uppercase tracking-widest text-parchment/40 font-bold">{label}</p>
      <h3 className="text-2xl font-display font-bold text-cloud">{value}</h3>
      <p className="text-[10px] text-parchment/30 mt-1">{sub}</p>
    </div>
  );
}

function IntegrityLine({ label, value }: { label: string, value: string }) {
  return (
    <div className="flex justify-between items-center border-b border-white/5 pb-2">
      <span className="text-[10px] text-parchment/40">{label}</span>
      <span className="text-[10px] font-mono text-parchment/60">{value}</span>
    </div>
  );
}

function ChevronDown(props: any) {
  return <svg {...props} width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="lucide lucide-chevron-down"><path d="m6 9 6 6 6-6" /></svg>;
}
