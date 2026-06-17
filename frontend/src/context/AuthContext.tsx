import { createContext, useContext, useState, type ReactNode } from 'react';

export type UserRole = 'employee' | 'manager' | 'finance' | null;

interface AuthContextType {
  role: UserRole;
  setRole: (role: UserRole) => void;
  userName: string | null;
  setUserName: (name: string | null) => void;
}

const AuthContext = createContext<AuthContextType>({
  role: null,
  setRole: () => {},
  userName: null,
  setUserName: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [role, setRole] = useState<UserRole>(null);
  const [userName, setUserName] = useState<string | null>(null);

  return (
    <AuthContext.Provider value={{ role, setRole, userName, setUserName }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
