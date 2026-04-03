const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export type DocumentItem = {
  id: string;
  logical_name: string;
  current_version: number;
  is_deleted: boolean;
  created_at: string;
  updated_at: string;
  filename?: string | null;
  file_type?: string | null;
  language?: string | null;
  chunk_count?: number | null;
  status?: string | null;
  uploaded_at?: string | null;
  active?: boolean;
};

export async function fetchDocuments(): Promise<DocumentItem[]> {
  const response = await fetch(`${API_BASE_URL}/documents`);
  if (!response.ok) {
    throw new Error(`Failed to fetch documents: ${response.status}`);
  }
  return response.json();
}

export async function uploadDocument(file: File, logicalName?: string, notes?: string): Promise<unknown> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('logical_name', logicalName?.trim() || file.name.replace(/\.[^.]+$/, ''));
  if (notes?.trim()) {
    formData.append('notes', notes.trim());
  }

  const response = await fetch(`${API_BASE_URL}/documents`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Upload failed: ${response.status} ${errorText}`);
  }

  return response.json();
}

export async function rebuildIndex(): Promise<unknown> {
  const response = await fetch(`${API_BASE_URL}/admin/rebuild-index`, {
    method: 'POST',
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Rebuild failed: ${response.status} ${errorText}`);
  }

  return response.json();
}
