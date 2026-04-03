export type DocumentItem = {
  id: string
  logical_name: string
  current_version: number
  is_deleted: boolean
  created_at: string
  updated_at: string
}

export type DocumentVersionItem = {
  version_id: string
  document_id: string
  version: number
  filename: string
  file_type: string
  language: string
  chunk_count: number
  status: string
  created_at: string
  notes?: string | null
}

export type RebuildResponse = {
  message: string
  chunks_indexed?: number
}
