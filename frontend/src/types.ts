export type User = {
  username: string;
  role: "admin" | "employee";
};

export type Source = {
  label: string;
  filename: string;
  page_number: number | null;
  excerpt: string;
};

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  answerId?: string;
  feedback?: number;
};

export type PolicyDocument = {
  id: string;
  filename: string;
  category: string;
  access_level: "employee" | "admin";
  version: number;
  status: string;
  chunk_count: number;
  error_message: string | null;
  updated_at: string;
};

export type ManagedUser = {
  username: string;
  role: User["role"];
  is_active: boolean | number;
  created_at: string;
};

export type Dashboard = {
  statistics: {
    indexed_documents: number;
    chunks: number;
    successful_jobs: number;
    failed_jobs: number;
  };
  documents: PolicyDocument[];
  pending_cleanup: {
    document_id: string;
    version: number;
    filename: string;
    current_version: number;
    error_message: string;
  }[];
  failed_jobs: {
    id: string;
    filename: string;
    error_message: string;
    created_at: string;
  }[];
  users: ManagedUser[];
  max_upload_size_mb: number;
};

export type ApplicationSettings = {
  environment: string;
  embedding_model: string;
  gemini_model: string;
  retrieval_top_k: number;
  chunk_size: number;
  chunk_overlap: number;
  max_upload_size_mb: number;
  google_api_key_configured: boolean;
  last_indexing: string | null;
};
