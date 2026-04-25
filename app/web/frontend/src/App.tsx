import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import HeroPage from './pages/HeroPage';
import EmployeeDashboard from './pages/EmployeeDashboard';
import ManagerDashboard from './pages/ManagerDashboard';
import FinanceDashboard from './pages/FinanceDashboard';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HeroPage />} />
        <Route path="/employee" element={<EmployeeDashboard />} />
        <Route path="/manager" element={<ManagerDashboard />} />
        <Route path="/finance" element={<FinanceDashboard />} />
        <Route path="*" element={<Navigate to="/" />} />
      </Routes>
    </BrowserRouter>
  );
}
