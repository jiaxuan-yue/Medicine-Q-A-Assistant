import client from './client';
import type { ApiResponse, GraphEntity, GraphVisualization } from '../types';

export const graphApi = {
  searchEntities: (params: { q?: string; entity_type?: string }) =>
    client.get<ApiResponse<GraphEntity[]>>('/graph/entities', { params }),

  getEntityDetail: (name: string) =>
    client.get<ApiResponse<GraphEntity>>(`/graph/entities/${encodeURIComponent(name)}`),

  findPaths: (fromEntity: string, toEntity: string) =>
    client.get<ApiResponse<GraphEntity[][]>>('/graph/paths', {
      params: { from_entity: fromEntity, to_entity: toEntity },
    }),

  getVisualization: (params?: { entity_type?: string; limit?: number }) =>
    client.get<ApiResponse<GraphVisualization>>('/graph/visualization', { params }),

  createEntity: (entity: { name: string; type: string; aliases?: string[]; properties?: Record<string, unknown> }) =>
    client.post<ApiResponse<GraphEntity>>('/graph/entities', entity),

  createRelationship: (rel: { from_entity: string; to_entity: string; relation_type: string }) =>
    client.post<ApiResponse<void>>('/graph/relationships', rel),
};
