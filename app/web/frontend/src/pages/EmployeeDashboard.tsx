import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Plus, Search, FileText, Send, ChevronRight, History as HistoryIcon, Upload, Loader2, AlertTriangle, CheckCircle, XCircle, Trash2 } from 'lucide-react';
import { cn } from '../lib/utils';
import { BentoCard, Skeleton, StatusBadge } from '../components/DashboardElements';
import { fetchLedger, submitClaim, parseDocument, deleteClaim, clearHistory } from '../api/client';
import { useToast } from '../context/ToastContext';
import type { LedgerRecord, SubmitClaimResponse, IntelligenceReport } from '../api/types';
import { useAuth } from '../context/AuthContext';

export default function EmployeeDashboard() {
  const { userName } = useAuth();
  const toast = useToast();

  const greetingText = React.useMemo(() => {
    const hour = new Date().getHours();
    if (hour >= 5 && hour < 12) return "Good morning";
    if (hour >= 12 && hour < 17) return "Good afternoon";
    if (hour >= 17 && hour < 21) return "Good evening";
    return "Good night";
  }, []);

  const firstName = userName ? userName.split(' ')[0] : '';
  const displayGreeting = firstName ? `${greetingText}, ${firstName}` : `Hello there`;

  const [loading, setLoading] = useState(true);
  const [showWizard, setShowWizard] = useState(false);
  const [wizardStep, setWizardStep] = useState(1);
  const [claimText, setClaimText] = useState('');
  const [receiptText, setReceiptText] = useState('');
  const [receiptFile, setReceiptFile] = useState<File | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [submitResponse, setSubmitResponse] = useState<SubmitClaimResponse | null>(null);
  // Active claim stepper state (defaults = mock, updates after real submission)
  const [activeClaimId, setActiveClaimId] = useState('CLM-2024-047');
  const [activeClaimDecision, setActiveClaimDecision] = useState<string>('Processing');
  const [activeClaimTrace, setActiveClaimTrace] = useState<string[]>([]);
  // Agent intelligence card state
  const [intelligenceMsg, setIntelligenceMsg] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const ACCEPTED_MIME = new Set([
    'application/pdf',
    'application/msword',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  ]);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!ACCEPTED_MIME.has(file.type)) {
      toast('Only PDF or Word documents (.doc, .docx) are accepted.', 'error');
      setFileError('Only PDF or Word documents (.doc, .docx) are accepted.');
      setReceiptFile(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
      return;
    }

    setFileError(null);
    setReceiptFile(file);
    try {
      const parsed = await parseDocument(file);
      setReceiptText(parsed.text);
    } catch (err) {
      console.warn('Failed to parse document:', err);
    }
  };

  const handleContinue = async () => {
    if (wizardStep === 1) {
      setIsSubmitting(true);
      setSubmitError(null);
      setWizardStep(2);
      try {
        const res = await submitClaim({
          employee_id: 'sarah_chen',
          employee_name: 'Sarah Chen',
          employee_team: 'Product',
          free_text: claimText,
          receipt_text: receiptText || undefined,
          attachments: receiptFile ? [receiptFile.name] : [],
        });
        setSubmitResponse(res);
        // Update stepper
        setActiveClaimId(res.claim_id);
        setActiveClaimTrace(res.trace || []);
        setActiveClaimDecision(res.approval?.decision ?? 'Processing');
        toast('Claim submitted successfully', 'success');
        // Update intelligence card
        const intel = res.intelligence;
        if (intel?.is_likely_duplicate && intel.duplicate_matches.length > 0) {
          setIntelligenceMsg(`Potential duplicate detected: "${intel.duplicate_matches[0].existing_product}" already exists in ${intel.duplicate_matches[0].owner_team}. ${intel.rationale}`);
        } else if (intel?.alternatives && intel.alternatives.length > 0) {
          const alt = intel.alternatives[0];
          setIntelligenceMsg(`Suggestion: Switch to "${alt.product}" — ${alt.reason}${alt.estimated_savings_myr ? ` (Save RM ${alt.estimated_savings_myr.toFixed(2)})` : ''}.`);
        } else {
          setIntelligenceMsg('No issues detected. Your claim looks clean.');
        }
      } catch (err: any) {
        setSubmitError(err?.message ?? 'Submission failed. Please try again.');
        toast(err?.message ?? 'Submission failed.', 'error');
      } finally {
        setIsSubmitting(false);
      }
    } else if (wizardStep === 2) {
      setWizardStep(3);
    } else {
      setShowWizard(false);
    }
  };

  const handleClearHistory = async () => {
    setIsClearing(true);
    try {
      await clearHistory('sarah_chen');
      setLedgerRecords([]);
      setShowClearConfirm(false);
      toast('History cleared', 'info');
    } catch (err) {
      console.warn('Failed to clear history:', err);
      toast('Failed to clear history', 'error');
    } finally {
      setIsClearing(false);
    }
  };

  const handleDeleteRecord = async (claimId: string) => {
    setDeletingId(claimId);
    try {
      await deleteClaim(claimId);
      setLedgerRecords(prev => prev.filter(r => r.claim_id !== claimId));
      toast('Claim deleted', 'info');
    } catch (err) {
      console.warn('Failed to delete record:', err);
      toast('Failed to delete record', 'error');
    } finally {
      setDeletingId(null);
      setConfirmDeleteId(null);
    }
  };

  const resetWizard = () => {
    setShowWizard(false);
    setWizardStep(1);
    setClaimText('');
    setReceiptText('');
    setReceiptFile(null);
    setSubmitError(null);
    setFileError(null);
    setSubmitResponse(null);
    setIsSubmitting(false);
  };

  // Fallback mock data shaped like LedgerRecord for when the API is unreachable
  const [ledgerRecords, setLedgerRecords] = useState<LedgerRecord[]>([
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

  useEffect(() => {
    const timer = setTimeout(() => setLoading(false), 1500);
    return () => clearTimeout(timer);
  }, []);

  // Fetch real ledger data from the backend API on mount and poll every 20 seconds
  useEffect(() => {
    const poll = () => {
      fetchLedger()
        .then((data) => {
          if (data.records && data.records.length > 0) {
            setLedgerRecords((prev) => {
              if (data.records.length !== prev.length || data.records[0]?.claim_id !== prev[0]?.claim_id) {
                return data.records;
              }
              return prev;
            });
          }
        })
        .catch((err) => {
          console.warn('Ledger API unavailable, using fallback mock data:', err.message);
        });
    };

    poll();
    const interval = setInterval(poll, 20000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return <EmployeeSkeleton />;
  }

  return (
    <div className="bg-charcoal min-h-screen">
      <main className="p-6 md:p-10 max-w-7xl mx-auto w-full relative">
        <header className="mb-10 flex flex-col md:flex-row md:items-end justify-between gap-6">
          <div>
            <h1 className="text-3xl md:text-4xl font-display font-bold">{displayGreeting}</h1>
            <p className="text-parchment/50 mt-2">You have 1 active claim in review.</p>
          </div>
        </header>

        <div className="grid grid-cols-1 md:grid-cols-12 gap-6 auto-rows-[minmax(180px,auto)]">
          {/* Active Claim Timeline */}
          <BentoCard title="Current Process" className="md:col-span-8 md:row-span-2">
            <div className="flex flex-col h-full bg-cloud/[0.02] rounded-xl p-6 border border-white/5">
              <div className="flex justify-between items-start mb-12">
                <div>
                  <h4 className="text-lg font-display font-semibold">{activeClaimId}</h4>
                  <p className="text-xs text-parchment/40">Submitted April 20, 2026</p>
                </div>
                <StatusBadge status={activeClaimDecision} />
              </div>

              <div className="relative flex-1 py-4">
                <div className="absolute left-[3px] top-4 bottom-4 w-[2px] bg-white/5" />
                <div className="space-y-8 relative">
                  <TimelineNode label="Claim Submitted" date="10:00 AM" active completed />
                  <TimelineNode label="AI Parsing & Extraction" date="10:05 AM" active={activeClaimTrace.length > 1 || activeClaimTrace.length === 0} completed={activeClaimTrace.some(t => t.includes('intake') || t.includes('extract'))} />
                  <TimelineNode label="Policy Validation" date="10:10 AM" active={activeClaimTrace.some(t => t.includes('policy'))} completed={activeClaimTrace.some(t => t.includes('policy'))} />
                  <TimelineNode label="Manager Review" date={activeClaimDecision === 'escalate_manager' ? 'Escalated' : 'Pending'} active={activeClaimDecision === 'escalate_manager'} />
                  <TimelineNode label="Final Disbursement" date={activeClaimDecision === 'auto_approve' ? 'Approved' : 'Pending'} active={activeClaimDecision === 'auto_approve'} completed={activeClaimDecision === 'auto_approve'} />
                </div>
              </div>
            </div>
          </BentoCard>

          {/* Quick Stats */}
          <BentoCard title="Annual Budget" className="md:col-span-4 h-full">
            <div className="flex flex-col justify-end h-full">
              <p className="text-4xl font-display font-bold text-gold">$14,250</p>
              <p className="text-xs text-parchment/40 mt-1 uppercase tracking-widest">Utilized of $25,000</p>
              <div className="mt-4 w-full h-1 bg-white/5 rounded-full overflow-hidden">
                <div className="h-full bg-gold w-[57%]" />
              </div>
            </div>
          </BentoCard>

          {/* AI Insights Card */}
          <BentoCard title="Agent Intelligence" className="md:col-span-4 h-full bg-gold/5 border-gold/20">
            <div className="flex flex-col gap-3">
              <p className="text-sm italic leading-relaxed text-parchment/80">
                "{intelligenceMsg ?? 'We found a potential duplicate charge for \'Canva Pro\' across your department licenses. Consider switching to the team plan for 15% savings.'}"
              </p>
              <button className="text-[10px] uppercase tracking-widest font-bold text-gold flex items-center gap-1 mt-2">
                Review Suggestion <ChevronRight className="w-3 h-3" />
              </button>
            </div>
          </BentoCard>

          {/* History Masonry-like List */}
          <BentoCard
            title="History"
            className="md:col-span-12"
            action={
              <button
                onClick={() => setShowClearConfirm(true)}
                className="flex items-center gap-1 text-[10px] font-bold uppercase tracking-widest text-parchment/30 hover:text-red-400 transition-colors"
              >
                <Trash2 className="w-3 h-3" />
                Clear
              </button>
            }
          >
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
              {[...ledgerRecords]
                .sort((a, b) => new Date(b.recorded_at).getTime() - new Date(a.recorded_at).getTime())
                .map((record, i) => {
                  const isConfirming = confirmDeleteId === record.claim_id;
                  const isDeleting = deletingId === record.claim_id;

                  return (
                    <motion.div 
                      key={record.claim_id + '-' + i} 
                      initial={{ opacity: 0, y: 20 }}
                      whileInView={{ opacity: 1, y: 0 }}
                      viewport={{ once: true }}
                      transition={{ delay: i * 0.05, duration: 0.3 }}
                      className="relative group p-5 rounded-2xl bg-white/[0.03] border border-white/5 hover:border-gold/30 hover:bg-white/[0.05] transition-all cursor-pointer"
                    >
                      {/* Inline delete confirm overlay */}
                      {isConfirming && (
                        <div className="absolute inset-0 rounded-2xl bg-charcoal/90 backdrop-blur-sm flex flex-col items-center justify-center gap-3 z-10">
                          <p className="text-xs text-parchment/60">Delete this record?</p>
                          <div className="flex gap-2">
                            <button
                              onClick={(e) => { e.stopPropagation(); setConfirmDeleteId(null); }}
                              className="px-3 py-1 text-[10px] rounded-lg bg-white/10 text-parchment/60 hover:bg-white/20 transition-colors"
                            >
                              Cancel
                            </button>
                            <button
                              onClick={(e) => { e.stopPropagation(); handleDeleteRecord(record.claim_id); }}
                              disabled={isDeleting}
                              className="px-3 py-1 text-[10px] rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors disabled:opacity-50"
                            >
                              {isDeleting ? 'Deleting…' : 'Delete'}
                            </button>
                          </div>
                        </div>
                      )}
                      <div className="flex justify-between mb-4 items-center">
                        <div className="w-10 h-10 rounded-xl bg-gold/10 flex items-center justify-center text-gold">
                          <HistoryIcon className="w-5 h-5" />
                        </div>
                        <div className="flex items-center gap-3">
                          <StatusBadge status={record.decision} />
                          {!isConfirming && (
                            <button
                              onClick={(e) => { e.stopPropagation(); setConfirmDeleteId(record.claim_id); }}
                              className="p-1.5 rounded-lg text-parchment/30 md:opacity-0 group-hover:opacity-100 hover:text-red-400 hover:bg-red-400/10 transition-all z-10"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </div>
                      </div>
                      <h5 className="font-medium text-sm mb-1 truncate">{record.vendor} — {record.product}</h5>
                      <p className="text-xs text-parchment/40 mb-4 line-clamp-2">
                        {new Date(record.recorded_at).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' })}
                      </p>
                      <p className="text-lg font-display font-bold text-gold">
                        RM {record.amount_myr.toFixed(2)}
                      </p>
                    </motion.div>
                  );
                })}
              <div className="p-5 rounded-2xl border border-dashed border-white/10 flex flex-col items-center justify-center gap-2 group hover:border-gold/50 cursor-pointer transition-all">
                <div className="w-10 h-10 rounded-xl bg-white/5 flex items-center justify-center text-parchment/40 group-hover:text-gold">
                  <Plus className="w-5 h-5" />
                </div>
                <span className="text-[10px] font-bold uppercase tracking-widest text-parchment/40 group-hover:text-gold transition-colors">View All History</span>
              </div>
            </div>
          </BentoCard>
        </div>

        {/* FAB */}
        <motion.button
          whileHover={{ scale: 1.1 }}
          whileTap={{ scale: 0.9 }}
          onClick={() => {
            setShowWizard(true);
            setWizardStep(1);
          }}
          className="fixed bottom-10 right-10 w-16 h-16 rounded-2xl bg-gold text-charcoal shadow-2xl shadow-gold/20 flex items-center justify-center hover:shadow-gold/40 transition-shadow z-40"
        >
          <Plus className="w-8 h-8" />
        </motion.button>

        {/* Clear History Confirmation Modal */}
        <AnimatePresence>
          {showClearConfirm && (
            <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                onClick={() => setShowClearConfirm(false)}
                className="absolute inset-0 bg-charcoal/80 backdrop-blur-md"
              />
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.95 }}
                className="relative bg-charcoal border border-white/10 rounded-2xl p-8 max-w-sm w-full shadow-2xl"
              >
                <div className="w-10 h-10 rounded-xl bg-red-500/10 flex items-center justify-center text-red-400 mb-4">
                  <Trash2 className="w-5 h-5" />
                </div>
                <h3 className="font-display font-bold mb-2">Clear All History?</h3>
                <p className="text-sm text-parchment/50 mb-6">
                  This will permanently delete all claim records. This cannot be undone.
                </p>
                <div className="flex gap-3 justify-end">
                  <button
                    onClick={() => setShowClearConfirm(false)}
                    className="px-4 py-2 text-sm text-parchment/50 hover:text-white transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleClearHistory}
                    disabled={isClearing}
                    className="px-5 py-2 text-sm font-bold bg-red-500/20 text-red-400 rounded-xl hover:bg-red-500/30 transition-colors disabled:opacity-50"
                  >
                    {isClearing ? 'Clearing…' : 'Clear History'}
                  </button>
                </div>
              </motion.div>
            </div>
          )}
        </AnimatePresence>

        {/* Wizard Modal */}
        <AnimatePresence>
          {showWizard && (
            <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
              <motion.div
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                onClick={() => setShowWizard(false)}
                className="absolute inset-0 bg-charcoal/80 backdrop-blur-md"
              />
              <motion.div
                initial={{ opacity: 0, scale: 0.95, y: 20 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 20 }}
                className="relative w-full max-w-2xl bg-charcoal border border-white/10 shadow-2xl rounded-3xl overflow-hidden"
              >
                <div className="p-8 border-b border-white/5 bg-white/[0.02] flex justify-between items-center">
                  <div>
                    <h2 className="text-xl font-display font-bold">New Reimbursement Claim</h2>
                    <p className="text-[10px] uppercase tracking-[0.2em] text-parchment/40 mt-1">
                      Step {wizardStep} of 3
                    </p>
                  </div>
                  <button onClick={() => setShowWizard(false)} className="text-parchment/30 hover:text-white transition-colors">
                    Cancel
                  </button>
                </div>

                <div className="p-8 min-h-[320px]">
                  {wizardStep === 1 && (
                    <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} className="space-y-6">
                      <p className="text-sm text-parchment/60">Describe your expenses in natural language. Our agents will parse and categorize them for you.</p>
                      <textarea
                        value={claimText}
                        onChange={(e) => setClaimText(e.target.value)}
                        placeholder="I spent $45 on a client dinner at Joe's Pizza last night and bought a $15 notebook on Amazon..."
                        className="w-full h-40 bg-white/5 border border-white/10 rounded-2xl p-6 text-sm text-cloud focus:border-gold/50 focus:ring-0 outline-none transition-all placeholder:text-parchment/20 resize-none"
                      />
                      <div className="flex items-center gap-3">
                        <input
                          ref={fileInputRef}
                          type="file"
                          accept=".pdf,.doc,.docx,application/pdf,application/msword,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                          onChange={handleFileChange}
                          className="hidden"
                        />
                        <button
                          onClick={() => fileInputRef.current?.click()}
                          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-white/5 border border-white/10 text-xs text-parchment/60 hover:border-gold/40 hover:text-parchment transition-all"
                        >
                          <Upload className="w-3.5 h-3.5" />
                          {receiptFile ? receiptFile.name : 'Attach Proof (PDF / DOC)'}
                        </button>
                        {receiptFile && <span className="text-[10px] text-green-400 uppercase tracking-widest">Parsed ✓</span>}
                      </div>
                      {fileError && <p className="text-xs text-red-400 mt-2">{fileError}</p>}
                    </motion.div>
                  )}

                  {wizardStep === 2 && (
                    <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} className="space-y-4">
                      <div className="flex items-center gap-2 mb-4">
                        <div className="w-8 h-8 rounded-lg bg-gold/10 flex items-center justify-center text-gold">
                          {isSubmitting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                        </div>
                        <h4 className="text-xs font-bold uppercase tracking-widest text-gold text-glow">
                          {isSubmitting ? 'Processing with AI Agents...' : 'Agent Parsing & Extraction'}
                        </h4>
                      </div>
                      {isSubmitting && (
                        <div className="flex flex-col items-center justify-center py-10 gap-3">
                          <Loader2 className="w-10 h-10 animate-spin text-gold/60" />
                          <p className="text-xs text-parchment/40 uppercase tracking-widest">Running workflow agents...</p>
                        </div>
                      )}
                      {!isSubmitting && submitError && (
                        <div className="flex items-start gap-3 p-4 rounded-xl bg-red-500/10 border border-red-500/20">
                          <AlertTriangle className="w-4 h-4 text-red-400 mt-0.5 shrink-0" />
                          <div>
                            <p className="text-xs font-bold text-red-400 mb-1">Submission Failed</p>
                            <p className="text-xs text-parchment/50">{submitError}</p>
                          </div>
                        </div>
                      )}
                      {!isSubmitting && !submitError && submitResponse?.intake && (
                        <div className="space-y-3">
                          <ExtractionItem
                            vendor={submitResponse.intake.vendor ?? 'Unknown'}
                            product={submitResponse.intake.product ?? ''}
                            amount={submitResponse.intake.amount_myr ?? 0}
                            currency={submitResponse.intake.currency_original ?? 'MYR'}
                            category={submitResponse.intake.category ?? 'other'}
                            confidence={submitResponse.intake.confidence}
                            hasDuplicate={submitResponse.intelligence?.is_likely_duplicate ?? false}
                          />
                          {submitResponse.intelligence?.is_likely_duplicate && (
                            <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-yellow-500/10 border border-yellow-500/20">
                              <AlertTriangle className="w-3.5 h-3.5 text-yellow-400 shrink-0" />
                              <p className="text-[10px] text-yellow-400">{submitResponse.intelligence.rationale}</p>
                            </div>
                          )}
                        </div>
                      )}
                      {!isSubmitting && !submitError && !submitResponse?.intake && (
                        <p className="text-xs text-parchment/30 italic">No structured data extracted.</p>
                      )}
                    </motion.div>
                  )}

                  {wizardStep === 3 && (
                    <motion.div initial={{ opacity: 0, x: 20 }} animate={{ opacity: 1, x: 0 }} className="flex flex-col items-center justify-center h-48 gap-4">
                      <div className={cn(
                        "w-16 h-16 rounded-full flex items-center justify-center",
                        submitResponse?.approval?.decision === 'auto_approve' ? 'bg-green-500/20 text-green-400' :
                          submitResponse?.approval?.decision === 'auto_reject' ? 'bg-red-500/20 text-red-400' :
                            'bg-gold/20 text-gold'
                      )}>
                        {submitResponse?.approval?.decision === 'auto_approve' ? <CheckCircle className="w-8 h-8" /> :
                          submitResponse?.approval?.decision === 'auto_reject' ? <XCircle className="w-8 h-8" /> :
                            <FileText className="w-8 h-8" />}
                      </div>
                      <div className="text-center">
                        <h4 className="text-lg font-bold">
                          {submitResponse?.approval?.decision === 'auto_approve' ? 'Claim Approved' :
                            submitResponse?.approval?.decision === 'auto_reject' ? 'Claim Rejected' :
                              submitResponse?.approval?.decision === 'escalate_manager' ? 'Escalated to Manager' :
                                submitResponse?.approval?.decision === 'escalate_finance' ? 'Sent to Finance Review' :
                                  'Decision Pending'}
                        </h4>
                        <p className="text-sm text-parchment/40 mt-1 max-w-sm">
                          {submitResponse?.approval?.reason ?? 'Your claim has been submitted and is under review.'}
                        </p>
                        {submitResponse?.claim_id && (
                          <p className="text-[10px] uppercase tracking-widest text-parchment/30 mt-3">{submitResponse.claim_id}</p>
                        )}
                      </div>
                    </motion.div>
                  )}
                </div>

                <div className="p-8 border-t border-white/5 bg-white/[0.01] flex justify-between">
                  <button
                    onClick={() => wizardStep > 1 && !isSubmitting && setWizardStep(wizardStep - 1)}
                    className={cn(
                      "px-6 py-2 text-sm font-medium text-parchment/40 hover:text-white transition-colors",
                      (wizardStep === 1 || wizardStep === 3) && "invisible"
                    )}
                  >
                    Back
                  </button>
                  <button
                    onClick={wizardStep === 3 ? resetWizard : handleContinue}
                    disabled={isSubmitting || (wizardStep === 1 && !claimText.trim())}
                    className="px-8 py-3 bg-gold text-charcoal rounded-xl font-bold text-sm flex items-center gap-2 hover:scale-[1.05] active:scale-95 transition-all shadow-lg shadow-gold/10 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100"
                  >
                    {isSubmitting ? (
                      <><Loader2 className="w-4 h-4 animate-spin" /> Processing...</>
                    ) : wizardStep === 3 ? (
                      <>View in History <ChevronRight className="w-4 h-4" /></>
                    ) : wizardStep === 2 ? (
                      <>Continue <ChevronRight className="w-4 h-4" /></>
                    ) : (
                      <>Continue <ChevronRight className="w-4 h-4" /></>
                    )}
                  </button>
                </div>
              </motion.div>
            </div>
          )}
        </AnimatePresence>
      </main>
    </div>
  );
}

function TimelineNode({ label, date, active, completed }: { label: string, date: string, active?: boolean, completed?: boolean }) {
  return (
    <div className="flex items-center gap-6 group">
      <div className={cn(
        "w-2 h-2 rounded-full z-10 transition-all duration-500",
        completed ? "bg-gold scale-125 shadow-[0_0_12px_rgba(247,200,115,1)]" :
          active ? "bg-gold/40 animate-pulse border border-gold" : "bg-white/10"
      )} />
      <div>
        <h5 className={cn(
          "text-[10px] font-bold uppercase tracking-widest transition-colors",
          active || completed ? "text-cloud" : "text-parchment/20"
        )}>
          {label}
        </h5>
        <p className="text-[10px] text-parchment/30">{date}</p>
      </div>
    </div>
  );
}

function ExtractionItem({
  vendor, product, amount, currency, category, confidence, hasDuplicate,
}: {
  vendor: string; product: string; amount: number; currency: string;
  category: string; confidence: number; hasDuplicate: boolean;
}) {
  const pct = Math.round(confidence * 100);
  const confColor = pct >= 80 ? 'text-green-400' : pct >= 50 ? 'text-yellow-400' : 'text-red-400';
  return (
    <div className={cn(
      "flex items-center justify-between p-4 rounded-xl bg-white/5 border transition-colors",
      hasDuplicate ? "border-yellow-500/30" : "border-white/5 hover:border-white/10"
    )}>
      <div className="flex items-center gap-4">
        <div className="w-8 h-8 rounded-lg bg-parchment/10 flex items-center justify-center text-[10px] font-bold">
          {vendor[0]?.toUpperCase()}
        </div>
        <div>
          <p className="text-xs font-bold">{vendor}{product ? ` — ${product}` : ''}</p>
          <p className="text-[9px] uppercase tracking-tighter text-parchment/40">{category}</p>
        </div>
      </div>
      <div className="flex flex-col items-end gap-1">
        <p className="text-sm font-display font-bold text-gold">
          {currency !== 'MYR' ? `${currency} ` : 'RM '}
          {amount.toFixed(2)}
        </p>
        <span className={cn("text-[9px] uppercase tracking-widest font-bold", confColor)}>
          {pct}% conf
        </span>
      </div>
    </div>
  );
}

function EmployeeSkeleton() {
  return (
    <div className="bg-charcoal min-h-screen">
      <main className="p-10 max-w-7xl mx-auto w-full">
        <div className="space-y-4 mb-12">
          <Skeleton className="w-64 h-10" />
          <Skeleton className="w-48 h-4 opacity-50" />
        </div>
        <div className="grid grid-cols-12 gap-8">
          <Skeleton className="col-span-8 h-[400px]" />
          <div className="col-span-4 space-y-8">
            <Skeleton className="h-[180px]" />
            <Skeleton className="h-[180px]" />
          </div>
          <Skeleton className="col-span-12 h-64" />
        </div>
      </main>
    </div>
  );
}
