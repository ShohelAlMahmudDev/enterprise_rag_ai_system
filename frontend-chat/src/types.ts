export type SourceItem = {
  logical_name?: string;
  filename?: string;
  chunk_id?: string | number;
  preview?: string;
  score?: number;
};

export type QueryResponse = {
  answer: string;
  language?: string;
  sources: string[] | SourceItem[];
  tool_used?: string;
};
