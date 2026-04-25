import { useState } from 'react';
import { motion, useScroll, useTransform, AnimatePresence } from 'motion/react';
import { Eye, EyeOff } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { cn } from '../lib/utils';
import { useAuth } from '../context/AuthContext';
import { useToast } from '../context/ToastContext';

export default function HeroPage() {
  const navigate = useNavigate();
  const { setRole, setUserName } = useAuth();
  const toast = useToast();
  const { scrollY } = useScroll();

  const [selectedRole, setSelectedRole] = useState<'employee' | 'manager' | 'finance' | null>(null);
  const [formData, setFormData] = useState({
    fullName: '',
    employeeId: '',
    managerId: '',
    department: '',
    team: '',
    email: '',
    contact: '',
    authCode: ''
  });
  const [errors, setErrors] = useState<Record<string, string>>({});

  const handleRoleSelect = (role: 'employee' | 'manager' | 'finance') => {
    setSelectedRole(role);
    setErrors({});
  };

  const handleSignIn = () => {
    const newErrors: Record<string, string> = {};
    if (!formData.fullName.trim()) newErrors.fullName = "This field is required.";

    if (selectedRole === 'employee') {
      if (!formData.employeeId.trim()) newErrors.employeeId = "This field is required.";
      if (!formData.department) newErrors.department = "This field is required.";
      if (!formData.contact.trim()) newErrors.contact = "This field is required.";
    } else if (selectedRole === 'manager') {
      if (!formData.managerId.trim()) newErrors.managerId = "This field is required.";
      if (!formData.team.trim()) newErrors.team = "This field is required.";
      if (!formData.email.trim()) newErrors.email = "This field is required.";
    } else if (selectedRole === 'finance') {
      if (!formData.employeeId.trim()) newErrors.employeeId = "This field is required.";
      if (!formData.department) newErrors.department = "This field is required.";
      if (!formData.contact.trim()) newErrors.contact = "This field is required.";
      if (!formData.authCode.trim()) newErrors.authCode = "This field is required.";
    }

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      toast('Please fill in all required fields.', 'error');
      return;
    }

    setUserName(formData.fullName.trim());
    setRole(selectedRole!);
    toast(`Welcome, ${formData.fullName.trim().split(' ')[0]}`, 'success');
    navigate(`/${selectedRole}`);
  };

  const DEPARTMENTS = ["Engineering", "Marketing", "Finance", "HR", "Operations", "Sales", "Legal", "IT"];
  
  // Parallax effects
  const yOrion = useTransform(scrollY, [0, 500], [0, 200]);
  const opacityOrion = useTransform(scrollY, [0, 300], [1, 0]);
  const scaleOrion = useTransform(scrollY, [0, 500], [1, 1.2]);

  const marqueeText = [
    "Multi-Agent Orchestration",
    "Intelligent Reimbursement",
    "Policy Compliance",
    "Procurement Intelligence"
  ];

  return (
    <div className="relative min-h-[200vh] bg-charcoal overflow-hidden selection:bg-gold/30">
      {/* Background Glow */}
      <div className="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-gold/5 rounded-full blur-[120px]" />
      <div className="absolute bottom-[20%] right-[-10%] w-[30%] h-[30%] bg-gold/5 rounded-full blur-[120px]" />

      {/* Hero Section */}
      <section className="h-screen flex flex-col items-center justify-center relative">
        <motion.div
          style={{ y: yOrion, opacity: opacityOrion, scale: scaleOrion }}
          className="text-center z-10"
        >
          <h1 className="text-[12vw] font-display font-bold tracking-tighter leading-none text-cloud gold-glow select-none">
            ORION
          </h1>
          <p className="mt-4 text-parchment/60 font-display uppercase tracking-[0.4em] text-sm md:text-base">
            Intelligent Workflow Engine
          </p>
        </motion.div>

        {/* Scroll Indicator */}
        <motion.div 
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 1, duration: 1 }}
          className="absolute bottom-10 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2"
        >
          <span className="text-[10px] uppercase tracking-widest text-parchment/40">Scroll to Explore</span>
          <div className="w-px h-12 bg-gradient-to-b from-parchment/40 to-transparent" />
        </motion.div>
      </section>

      {/* Marquee Section */}
      <div className="py-12 border-y border-white/5 bg-white/[0.02] relative overflow-hidden">
        <div className="flex animate-marquee whitespace-nowrap">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="flex items-center gap-12 px-6">
              {marqueeText.map((text, idx) => (
                <div key={idx} className="flex items-center gap-8">
                  <span className="text-2xl md:text-4xl font-display font-medium text-parchment flex items-center gap-8">
                    {text}
                    <span className="w-2 h-2 rounded-full bg-gold shadow-[0_0_8px_rgba(247,200,115,0.8)]" />
                  </span>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>

      {/* Sign-In Section */}
      <section className="min-h-screen flex items-center justify-center px-4 relative">
        <div className="absolute inset-0 bg-radial-gradient from-gold/5 to-transparent pointer-events-none" />
        
        <motion.div 
          initial={{ opacity: 0, y: 40 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="glass-card w-full max-w-lg rounded-3xl p-8 md:p-12 text-center"
        >
          <AnimatePresence mode="wait">
            {!selectedRole ? (
              <motion.div 
                key="role-select"
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -20 }}
                className="space-y-4"
              >
                <h2 className="text-3xl font-display font-semibold mb-2">Welcome Back</h2>
                <p className="text-parchment/60 mb-10 text-sm">Select your gateway to the orchestration engine.</p>
                
                <RoleButton 
                  label="Sign in as Employee" 
                  onClick={() => handleRoleSelect('employee')} 
                />
                <RoleButton 
                  label="Sign in as Manager" 
                  onClick={() => handleRoleSelect('manager')} 
                />
                <RoleButton 
                  label="Sign in as Finance" 
                  onClick={() => handleRoleSelect('finance')} 
                />
              </motion.div>
            ) : (
              <motion.div
                key="role-details"
                initial={{ opacity: 0, x: 20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
                className="text-left space-y-4"
              >
                <button 
                  onClick={() => setSelectedRole(null)}
                  className="text-xs text-parchment/40 hover:text-gold mb-2 inline-block transition-colors"
                >
                  ← Back to roles
                </button>
                <h2 className="text-2xl font-display font-semibold mb-6 text-center capitalize">
                  {selectedRole} Sign In
                </h2>

                <div className="space-y-3 pb-4">
                  <InputField 
                    label="Full Name" 
                    value={formData.fullName} 
                    onChange={(e) => setFormData({...formData, fullName: e.target.value})} 
                    error={errors.fullName}
                  />

                  {selectedRole === 'employee' && (
                    <>
                      <InputField 
                        label="Employee ID" 
                        value={formData.employeeId} 
                        onChange={(e) => setFormData({...formData, employeeId: e.target.value})} 
                        error={errors.employeeId}
                      />
                      <SelectField
                        label="Department"
                        value={formData.department}
                        onChange={(e) => setFormData({...formData, department: e.target.value})}
                        options={DEPARTMENTS}
                        error={errors.department}
                      />
                      <InputField 
                        label="Email or Phone Number" 
                        value={formData.contact} 
                        onChange={(e) => setFormData({...formData, contact: e.target.value})} 
                        error={errors.contact}
                      />
                    </>
                  )}

                  {selectedRole === 'manager' && (
                    <>
                      <InputField 
                        label="Manager ID" 
                        value={formData.managerId} 
                        onChange={(e) => setFormData({...formData, managerId: e.target.value})} 
                        error={errors.managerId}
                      />
                      <InputField 
                        label="Team / Division" 
                        value={formData.team} 
                        onChange={(e) => setFormData({...formData, team: e.target.value})} 
                        error={errors.team}
                      />
                      <InputField 
                        label="Email" 
                        type="email"
                        value={formData.email} 
                        onChange={(e) => setFormData({...formData, email: e.target.value})} 
                        error={errors.email}
                      />
                    </>
                  )}

                  {selectedRole === 'finance' && (
                    <>
                      <InputField 
                        label="Employee ID" 
                        value={formData.employeeId} 
                        onChange={(e) => setFormData({...formData, employeeId: e.target.value})} 
                        error={errors.employeeId}
                      />
                      <SelectField
                        label="Department"
                        value={formData.department}
                        onChange={(e) => setFormData({...formData, department: e.target.value})}
                        options={DEPARTMENTS}
                        error={errors.department}
                      />
                      <InputField 
                        label="Email or Phone Number" 
                        value={formData.contact} 
                        onChange={(e) => setFormData({...formData, contact: e.target.value})} 
                        error={errors.contact}
                      />
                      <AuthCodeField
                        label="Authorization / Access Code"
                        value={formData.authCode}
                        onChange={(e) => setFormData({...formData, authCode: e.target.value})}
                        error={errors.authCode}
                      />
                    </>
                  )}
                </div>

                <RoleButton label="Continue to Dashboard" onClick={handleSignIn} />
              </motion.div>
            )}
          </AnimatePresence>
          
          <div className="mt-12 pt-8 border-t border-white/10">
            <p className="text-[10px] uppercase tracking-widest text-parchment/30">
              © 2026 ORION Intelligence Systems
            </p>
          </div>
        </motion.div>
      </section>
    </div>
  );
}

function RoleButton({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "group relative w-full h-14 rounded-xl flex items-center justify-center overflow-hidden transition-all duration-300",
        "bg-gold text-charcoal font-semibold hover:scale-[1.02] active:scale-95 shadow-[0_8px_16px_rgba(247,200,115,0.1)]"
      )}
    >
      <span className="relative z-10">{label}</span>
      <div className="absolute inset-0 bg-white opacity-0 group-hover:opacity-20 transition-opacity" />
    </button>
  );
}

function InputField({ label, value, onChange, error, type = "text", placeholder }: { label: string; value: string; onChange: (e: React.ChangeEvent<HTMLInputElement>) => void; error?: string; type?: string; placeholder?: string }) {
  return (
    <div className="flex flex-col text-left gap-1">
      <label className="text-xs text-parchment/60 ml-1">{label}</label>
      <input 
        type={type} 
        value={value} 
        onChange={onChange} 
        placeholder={placeholder}
        className={cn(
          "bg-white/5 border rounded-xl px-4 py-3 text-sm text-cloud focus:outline-none transition-colors placeholder:text-parchment/20",
          error ? "border-red-500/50 focus:border-red-500" : "border-white/10 focus:border-gold/50"
        )}
      />
      {error && <span className="text-[10px] text-red-400 ml-1">{error}</span>}
    </div>
  );
}

function SelectField({ label, value, onChange, options, error }: { label: string; value: string; onChange: (e: React.ChangeEvent<HTMLSelectElement>) => void; options: string[]; error?: string }) {
  return (
    <div className="flex flex-col text-left gap-1">
      <label className="text-xs text-parchment/60 ml-1">{label}</label>
      <select 
        value={value} 
        onChange={onChange} 
        className={cn(
          "bg-white/5 border rounded-xl px-4 py-3 text-sm focus:outline-none transition-colors appearance-none",
          error ? "border-red-500/50 focus:border-red-500" : "border-white/10 focus:border-gold/50",
          value === "" ? "text-parchment/40" : "text-cloud"
        )}
      >
        <option value="" disabled className="bg-charcoal text-parchment/40">Select department</option>
        {options.map(opt => (
          <option key={opt} value={opt} className="bg-charcoal text-cloud">{opt}</option>
        ))}
      </select>
      {error && <span className="text-[10px] text-red-400 ml-1">{error}</span>}
    </div>
  );
}

function AuthCodeField({ label, value, onChange, error }: { label: string; value: string; onChange: (e: React.ChangeEvent<HTMLInputElement>) => void; error?: string }) {
  const [show, setShow] = useState(false);
  return (
    <div className="flex flex-col text-left gap-1">
      <label className="text-xs text-parchment/60 ml-1">{label}</label>
      <div className="relative">
        <input 
          type={show ? "text" : "password"} 
          value={value} 
          onChange={onChange}
          autoComplete="off"
          className={cn(
            "w-full bg-white/5 border rounded-xl px-4 py-3 text-sm text-cloud focus:outline-none transition-colors pr-10",
            error ? "border-red-500/50 focus:border-red-500" : "border-white/10 focus:border-gold/50"
          )}
        />
        <button 
          type="button"
          onClick={() => setShow(!show)}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-parchment/40 hover:text-parchment transition-colors"
        >
          {show ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
        </button>
      </div>
      {error && <span className="text-[10px] text-red-400 ml-1">{error}</span>}
    </div>
  );
}
