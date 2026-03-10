import { useState, type FormEvent } from "react";
import { Navigate, Link } from "react-router-dom";
import { Shield, AlertCircle } from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import Button from "@/components/common/Button";

export default function Register() {
  const { register, isAuthenticated, isLoading: authLoading } = useAuth();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  if (authLoading) {
    return null;
  }

  if (isAuthenticated) {
    return <Navigate to="/" replace />;
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    if (password !== confirm) {
      setError("Passwords do not match");
      return;
    }

    setIsSubmitting(true);
    try {
      await register({ username, email, password });
    } catch (err: unknown) {
      if (err && typeof err === "object" && "response" in err) {
        const axiosErr = err as { response?: { data?: { detail?: string } } };
        setError(axiosErr.response?.data?.detail || "Registration failed");
      } else {
        setError("An unexpected error occurred. Please try again.");
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-lg bg-accent/10 mb-4">
            <Shield className="h-6 w-6 text-accent" />
          </div>
          <h1 className="font-mono font-bold text-xl text-text-primary tracking-wider">
            CYBERSEC PIPELINE
          </h1>
          <p className="text-text-secondary text-sm mt-1">Create your account</p>
        </div>

        {/* Register Form */}
        <form
          onSubmit={handleSubmit}
          className="bg-surface border border-border rounded-lg p-6 space-y-4"
        >
          <div>
            <label
              htmlFor="username"
              className="block text-xs font-mono font-medium text-text-secondary uppercase tracking-wider mb-1.5"
            >
              Username
            </label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoComplete="username"
              autoFocus
              className="w-full px-3 py-2 bg-background border border-border rounded text-text-primary text-sm font-mono placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-accent/50 focus:border-accent transition-colors"
              placeholder="Choose a username"
            />
          </div>

          <div>
            <label
              htmlFor="email"
              className="block text-xs font-mono font-medium text-text-secondary uppercase tracking-wider mb-1.5"
            >
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
              className="w-full px-3 py-2 bg-background border border-border rounded text-text-primary text-sm font-mono placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-accent/50 focus:border-accent transition-colors"
              placeholder="Enter your email"
            />
          </div>

          <div>
            <label
              htmlFor="password"
              className="block text-xs font-mono font-medium text-text-secondary uppercase tracking-wider mb-1.5"
            >
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              autoComplete="new-password"
              className="w-full px-3 py-2 bg-background border border-border rounded text-text-primary text-sm font-mono placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-accent/50 focus:border-accent transition-colors"
              placeholder="Create a password"
            />
          </div>

          <div>
            <label
              htmlFor="confirm"
              className="block text-xs font-mono font-medium text-text-secondary uppercase tracking-wider mb-1.5"
            >
              Confirm Password
            </label>
            <input
              id="confirm"
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              required
              autoComplete="new-password"
              className="w-full px-3 py-2 bg-background border border-border rounded text-text-primary text-sm font-mono placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-accent/50 focus:border-accent transition-colors"
              placeholder="Repeat your password"
            />
          </div>

          {error && (
            <div className="flex items-center gap-2 p-3 bg-severity-critical/10 border border-severity-critical/30 rounded text-sm text-severity-critical">
              <AlertCircle className="h-4 w-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <Button
            type="submit"
            className="w-full"
            size="lg"
            isLoading={isSubmitting}
          >
            Create Account
          </Button>
        </form>

        <p className="text-center text-text-muted text-xs mt-4 font-mono">
          Already have an account?{" "}
          <Link to="/login" className="text-accent hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
