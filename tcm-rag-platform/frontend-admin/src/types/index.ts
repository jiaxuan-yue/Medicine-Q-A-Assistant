export interface User {
  id: number;
  username: string;
  email: string;
  role: string;
  status: string;
  created_at: string;
}

export interface Document {
  doc_id: string;
  title: string;
  source: string;
  version: number;
  status: 'pending' | 'processing' | 'published' | 'rejected' | 'failed';
  authority_score: number;
  uploaded_by: string;
  published_at: string | null;
  created_at: string;
}

export interface DashboardStats {
  total_users: number;
  total_documents: number;
  total_sessions: number;
  total_messages: number;
  documents_pending_review: number;
  feedback_positive_rate: number;
}

export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
  trace_id: string;
}

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

// Knowledge Graph types
export interface GraphEntity {
  name: string;
  type: string;
  aliases?: string[];
  properties?: Record<string, unknown>;
  neighbors?: GraphRelation[];
}

export interface GraphRelation {
  from_entity: string;
  to_entity: string;
  relation_type: string;
  properties?: Record<string, unknown>;
}

export interface GraphVisualization {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface GraphNode {
  id: string;
  name: string;
  type: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  relation: string;
}

// Evaluation types
export interface EvalTask {
  id: string;
  eval_type: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  metrics?: EvalMetrics;
  dataset_path?: string;
  created_at: string;
  completed_at?: string;
}

export interface EvalMetrics {
  recall_at_5?: number;
  recall_at_10?: number;
  mrr?: number;
  ndcg?: number;
  [key: string]: number | undefined;
}

export interface EvalComparison {
  task_1: EvalTask;
  task_2: EvalTask;
}

// Feedback types
export interface FeedbackItem {
  id: number;
  query: string;
  answer: string;
  rating: number;
  category?: string;
  content?: string;
  created_at: string;
}

export interface FeedbackStats {
  total: number;
  positive: number;
  negative: number;
  by_category: Record<string, number>;
}

// Model Config types
export interface ModelConfigData {
  top_k: number;
  rerank_k: number;
  rrf_k: number;
  graph_max_hops: number;
  query_rewrite_enabled: boolean;
  graph_recall_enabled: boolean;
  reranker_enabled: boolean;
  llm_model: string;
  embedding_model: string;
  reranker_model: string;
}
