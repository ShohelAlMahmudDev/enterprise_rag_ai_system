import { useEffect, useMemo, useState } from 'react';
import { DatabaseZap, FileUp, RefreshCcw, ShieldCheck } from 'lucide-react';
import { fetchDocuments, rebuildIndex, uploadDocument, type DocumentItem } from './api';

export default function App() {
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [logicalName, setLogicalName] = useState('');
  const [notes, setNotes] = useState('');
  const [message, setMessage] = useState('');
  const [loading, setLoading] = useState(false);

  const totalActive = useMemo(
    () => documents.filter((item) => item.active !== false).length,
    [documents],
  );

  const loadDocuments = async () => {
    const data = await fetchDocuments();
    setDocuments(data);
  };

  useEffect(() => {
    loadDocuments().catch((err: unknown) => {
      setMessage(err instanceof Error ? err.message : 'Failed to load documents');
    });
  }, []);

  const handleFileSelect = (file: File | null) => {
    setSelectedFile(file);
    if (file && !logicalName.trim()) {
      setLogicalName(file.name.replace(/\.[^.]+$/, ''));
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) return;
    setLoading(true);
    setMessage('Uploading document…');

    try {
      await uploadDocument(selectedFile, logicalName, notes);
      setMessage('Document uploaded successfully.');
      setSelectedFile(null);
      setLogicalName('');
      setNotes('');
      await loadDocuments();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setLoading(false);
    }
  };

  const handleRebuild = async () => {
    setLoading(true);
    setMessage('Rebuilding vector index…');

    try {
      await rebuildIndex();
      setMessage('Index rebuilt successfully.');
      await loadDocuments();
    } catch (err) {
      setMessage(err instanceof Error ? err.message : 'Rebuild failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="admin-shell">
      <aside className="admin-sidebar">
        <div className="admin-brand">
          <ShieldCheck size={18} />
          <div>
            <strong>Enterprise RAG Admin</strong>
            <p>Manage uploads and index refresh</p>
          </div>
        </div>

        <div className="admin-stat-card">
          <span>Documents</span>
          <strong>{documents.length}</strong>
        </div>
        <div className="admin-stat-card">
          <span>Active</span>
          <strong>{totalActive}</strong>
        </div>
      </aside>

      <main className="admin-main">
        <header className="admin-header">
          <div>
            <p className="eyebrow">Administration</p>
            <h1>Document operations console</h1>
          </div>
          <div className="toolbar">
            <label className="upload-label">
              <FileUp size={16} />
              <span>{selectedFile ? selectedFile.name : 'Select file'}</span>
              <input type="file" onChange={(e) => handleFileSelect(e.target.files?.[0] ?? null)} hidden />
            </label>
            <button className="action-button primary" onClick={handleUpload} disabled={!selectedFile || loading}>
              <FileUp size={16} /> Upload
            </button>
            <button className="action-button" onClick={handleRebuild} disabled={loading}>
              <RefreshCcw size={16} /> Rebuild index
            </button>
          </div>
        </header>

        <section className="admin-kpis">
          <article className="kpi-card">
            <DatabaseZap size={18} />
            <div>
              <span>Vector store status</span>
              <strong>{loading ? 'Busy' : 'Ready'}</strong>
            </div>
          </article>
          <article className="kpi-card">
            <ShieldCheck size={18} />
            <div>
              <span>Recommended mode</span>
              <strong>Local / offline</strong>
            </div>
          </article>
        </section>

        <section className="table-card" style={{ marginBottom: 20 }}>
          <div className="table-header">
            <h2>New upload</h2>
            <span>Required before indexing</span>
          </div>
          <div style={{ display: 'grid', gap: 12 }}>
            <input
              value={logicalName}
              onChange={(e) => setLogicalName(e.target.value)}
              placeholder="Logical name"
              style={{ padding: 12, borderRadius: 12, border: '1px solid rgba(148, 163, 184, 0.18)', background: '#0a1326', color: 'inherit' }}
            />
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Notes (optional)"
              rows={3}
              style={{ padding: 12, borderRadius: 12, border: '1px solid rgba(148, 163, 184, 0.18)', background: '#0a1326', color: 'inherit', resize: 'vertical' }}
            />
          </div>
        </section>

        {message ? <div className="admin-banner">{message}</div> : null}

        <section className="table-card">
          <div className="table-header">
            <h2>Uploaded documents</h2>
            <span>{documents.length} items</span>
          </div>

          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Logical name</th>
                  <th>Filename</th>
                  <th>Version</th>
                  <th>Uploaded</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {documents.length ? (
                  documents.map((document) => (
                    <tr key={document.id}>
                      <td>{document.logical_name || '-'}</td>
                      <td>{document.filename || '-'}</td>
                      <td>{document.current_version ?? '-'}</td>
                      <td>{document.uploaded_at || document.updated_at || '-'}</td>
                      <td>
                        <span className={`status ${document.active === false ? 'inactive' : 'active'}`}>
                          {document.active === false ? 'Inactive' : document.status || 'Active'}
                        </span>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} className="empty-row">No documents available yet.</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </section>
      </main>
    </div>
  );
}
