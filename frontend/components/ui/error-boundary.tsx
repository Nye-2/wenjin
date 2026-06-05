"use client";

import { Component, ReactNode } from "react";
import { AlertTriangle } from "lucide-react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
  onRetry?: () => void;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: undefined });
    this.props.onRetry?.();
  };

  render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div className="wjn-hairline-panel rounded-[var(--wjn-radius-lg)] p-6 text-center">
          <AlertTriangle className="mx-auto mb-4 h-12 w-12 text-[var(--wjn-review)]" />
          <p className="mb-2 font-medium text-[var(--wjn-error)]">
            Something went wrong
          </p>
          <p className="mb-4 text-sm text-[var(--wjn-text-muted)]">
            {this.state.error?.message || "An unexpected error occurred"}
          </p>
          <button
            onClick={this.handleRetry}
            className="rounded-[var(--wjn-radius)] bg-[var(--wjn-blue)] px-4 py-2 text-white transition-colors hover:bg-[var(--wjn-accent-strong)]"
          >
            Try again
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
