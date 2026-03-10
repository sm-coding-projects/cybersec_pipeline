import { BrowserRouter, Routes, Route } from "react-router-dom";
import MainLayout from "@/components/layout/MainLayout";
import Login from "@/pages/Login";
import Register from "@/pages/Register";
import Dashboard from "@/pages/Dashboard";
import ScanNew from "@/pages/ScanNew";
import ScanDetail from "@/pages/ScanDetail";
import ScanHistory from "@/pages/ScanHistory";
import Findings from "@/pages/Findings";
import FindingDetail from "@/pages/FindingDetail";
import ToolStatus from "@/pages/ToolStatus";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Public routes */}
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />

        {/* Protected routes */}
        <Route element={<MainLayout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/scans/new" element={<ScanNew />} />
          <Route path="/scans/:id" element={<ScanDetail />} />
          <Route path="/scans" element={<ScanHistory />} />
          <Route path="/findings/:id" element={<FindingDetail />} />
          <Route path="/findings" element={<Findings />} />
          <Route path="/tools" element={<ToolStatus />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
