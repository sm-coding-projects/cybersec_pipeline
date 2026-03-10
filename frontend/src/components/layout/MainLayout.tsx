import { Outlet, Navigate } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import Sidebar from "./Sidebar";
import Header from "./Header";
import { FullPageSpinner } from "@/components/common/LoadingSpinner";

export default function MainLayout() {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return <FullPageSpinner />;
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="min-h-screen bg-background">
      <Sidebar />
      <Header />
      <main className="ml-56 mt-14 p-6">
        <Outlet />
      </main>
    </div>
  );
}
