import React from "react";

/**
 * Catches render/lifecycle errors thrown by whatever it wraps (e.g. one
 * tool's component tree) so a bug in a single tool shows an inline error
 * instead of an uncaught error unmounting the entire app to a blank page.
 *
 * Note: this only catches errors during React's render/commit phases, not
 * errors inside async code (e.g. a rejected fetch in a useEffect) — those
 * are expected to be caught locally and surfaced via each tool's own
 * tool-error UI, same as today.
 */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    // Keep this loud in the console — it's the only trace once React has
    // unmounted the broken subtree.
    console.error("Tool crashed:", error, info?.componentStack);
  }

  componentDidUpdate(prevProps) {
    // Let the parent recover by changing resetKey (e.g. when the user
    // navigates to a different tool) without a full page reload.
    if (this.state.error && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ error: null });
    }
  }

  render() {
    if (this.state.error) {
      return (
        <div className="tool-panel">
          <div className="tool-section-title">Something went wrong in this tool</div>
          <div className="tool-error">{this.state.error.message || String(this.state.error)}</div>
          <div className="tool-actions" style={{ marginTop: 14 }}>
            <button className="tool-btn tool-btn-ghost" onClick={() => this.setState({ error: null })}>
              Try again
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
