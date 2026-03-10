import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  PlusCircle,
  History,
  Shield,
  Server,
} from "lucide-react";

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/scans/new", icon: PlusCircle, label: "New Scan" },
  { to: "/scans", icon: History, label: "Scan History" },
  { to: "/findings", icon: Shield, label: "Findings" },
  { to: "/tools", icon: Server, label: "Tool Status" },
];

export default function Sidebar() {
  return (
    <aside className="fixed left-0 top-0 h-screen w-56 bg-surface border-r border-border flex flex-col z-30">
      {/* Logo */}
      <div className="h-14 flex items-center px-4 border-b border-border">
        <div className="flex items-center gap-2">
          <Shield className="h-5 w-5 text-accent" />
          <span className="font-mono font-bold text-sm text-text-primary tracking-wider">
            CYBERSEC
          </span>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4 px-2 space-y-1">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === "/"}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded text-sm font-medium transition-colors duration-150 ${
                isActive
                  ? "bg-accent/10 text-accent border-l-2 border-accent"
                  : "text-text-secondary hover:text-text-primary hover:bg-surface-elevated"
              }`
            }
          >
            <item.icon className="h-4 w-4 flex-shrink-0" />
            <span>{item.label}</span>
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-4 py-3 border-t border-border">
        <p className="text-[10px] text-text-muted font-mono">
          CyberSec Pipeline v1.0
        </p>
      </div>
    </aside>
  );
}
