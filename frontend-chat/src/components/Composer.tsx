import { FormEvent } from 'react';
import { ArrowUp, Paperclip } from 'lucide-react';

type ComposerProps = {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  loading: boolean;
};

export function Composer({ value, onChange, onSubmit, loading }: ComposerProps) {
  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!loading && value.trim()) {
      onSubmit();
    }
  };

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <div className="composer-input-wrap">
        <button type="button" className="icon-button muted" aria-label="Attachments disabled">
          <Paperclip size={18} />
        </button>
        <textarea
          value={value}
          onChange={(event) => onChange(event.target.value)}
          rows={1}
          placeholder="Ask about your internal documents…"
        />
        <button
          type="submit"
          className="icon-button primary"
          disabled={loading || !value.trim()}
          aria-label="Send"
        >
          <ArrowUp size={18} />
        </button>
      </div>
      <p className="composer-hint">
        Answers should stay grounded in uploaded sources. For admin tasks, use the separate admin app.
      </p>
    </form>
  );
}
