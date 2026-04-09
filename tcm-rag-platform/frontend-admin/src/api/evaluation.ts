import client from './client';
import type { ApiResponse, PaginatedResponse, EvalTask, EvalComparison } from '../types';

export const evaluationApi = {
  runEval: (evalType: string, datasetPath?: string) =>
    client.post<ApiResponse<EvalTask>>('/evaluation/run', {
      eval_type: evalType,
      dataset_path: datasetPath,
    }),

  listTasks: (params?: { page?: number; size?: number }) =>
    client.get<ApiResponse<PaginatedResponse<EvalTask>>>('/evaluation/tasks', { params }),

  getTaskDetail: (taskId: string) =>
    client.get<ApiResponse<EvalTask>>(`/evaluation/tasks/${taskId}`),

  compareTasks: (taskId1: string, taskId2: string) =>
    client.get<ApiResponse<EvalComparison>>('/evaluation/compare', {
      params: { task_id_1: taskId1, task_id_2: taskId2 },
    }),
};
