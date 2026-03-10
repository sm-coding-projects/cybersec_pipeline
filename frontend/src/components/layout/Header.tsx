import { LogOut, User } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import Button from "@/components/common/Button";

export default function Header() {
  const { user, logout } = useAuth();

  return (
    <header className="fixed top-0 left-56 right-0 h-14 bg-surface border-b border-border flex items-center justify-between px-6 z-20">
      <div>
        <h1 className="font-mono font-bold text-sm text-text-primary tracking-wider uppercase">
          CyberSec Pipeline
        </h1>
      </div>

      <div className="flex items-center gap-4">
        {user && (
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 text-text-secondary">
              <User className="h-4 w-4" />
              <span className="text-sm font-mono">{user.username}</span>
            </div>
            <Button variant="ghost" size="sm" onClick={logout}>
              <LogOut className="h-4 w-4 mr-1" />
              Logout
            </Button>
          </div>
        )}
      </div>
    </header>
  );
}
