import { apiRequest, routes } from './client';

export type RecommendationSourceType = 'SOCIAL' | 'CURATED';
export type RecommendationAction = 'NOT_INTERESTED' | 'HIDE' | 'SEARCH_CLICK';

export interface RecommendationActionInput {
  source_type: RecommendationSourceType;
  source_id: number;
  action: RecommendationAction;
}

export interface RecommendationActionResponse {
  ok: boolean;
}

/** Records a child's explicit recommendation feedback through the v2 contract. */
export function submitRecommendationAction(
  token: string,
  input: RecommendationActionInput,
): Promise<RecommendationActionResponse> {
  return apiRequest<RecommendationActionResponse>(
    routes.recommendationActions,
    { method: 'POST', body: JSON.stringify(input) },
    token,
  );
}