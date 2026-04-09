import type { ModelConfigData } from '../types';

const STORAGE_KEY = 'admin_model_config';

const DEFAULT_CONFIG: ModelConfigData = {
  top_k: 10,
  rerank_k: 5,
  rrf_k: 60,
  graph_max_hops: 2,
  query_rewrite_enabled: true,
  graph_recall_enabled: true,
  reranker_enabled: true,
  llm_model: 'qwen-plus',
  embedding_model: 'bge-large-zh-v1.5',
  reranker_model: 'bge-reranker-v2-m3',
};

export const configApi = {
  getConfig: (): ModelConfigData => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      try {
        return { ...DEFAULT_CONFIG, ...JSON.parse(stored) };
      } catch {
        return { ...DEFAULT_CONFIG };
      }
    }
    return { ...DEFAULT_CONFIG };
  },

  saveConfig: (config: ModelConfigData): void => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
  },

  getDefaultConfig: (): ModelConfigData => ({ ...DEFAULT_CONFIG }),
};
