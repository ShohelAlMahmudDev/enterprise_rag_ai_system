import type { SourceItem } from '../types';
import { FileText } from 'lucide-react';

type SourcesPanelProps = {
  sources: string[] | SourceItem[];
};

function isObjectSource(source: string | SourceItem): source is SourceItem {
  return typeof source !== 'string';
}

export function SourcesPanel({ sources }: SourcesPanelProps) {
  if (!sources.length) return null;

  return (
    <section className="sources-panel">
      <div className="section-header">
        <h3>Sources</h3>
        <span>{sources.length} attached</span>
      </div>
      <div className="source-grid">
        {sources.map((source, index) => {
          if (isObjectSource(source)) {
            return (
              <article className="source-card" key={`${source.filename}-${source.chunk_id}-${index}`}>
                <div className="source-card-top">
                  <FileText size={16} />
                  <span>{source.logical_name || 'Document'}</span>
                </div>
                <strong>{source.filename || 'Unknown file'}</strong>
                <p>Chunk: {source.chunk_id ?? '-'}</p>
                {typeof source.score === 'number' ? <p>Score: {source.score.toFixed(3)}</p> : null}
                {source.preview ? <small>{source.preview}</small> : null}
              </article>
            );
          }

          return (
            <article className="source-card" key={`${source}-${index}`}>
              <div className="source-card-top">
                <FileText size={16} />
                <span>Referenced source</span>
              </div>
              <strong>{source}</strong>
            </article>
          );
        })}
      </div>
    </section>
  );
}
