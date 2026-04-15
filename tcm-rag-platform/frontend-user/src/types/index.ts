export interface User {
  id: number;
  username: string;
  email: string;
  role: string;
}

export interface UserCaseProfile {
  id: number | null;
  user_id: number | null;
  gender: string | null;
  age: number | null;
  chief_complaint: string | null;
  symptom_duration: string | null;
  primary_symptoms: string[];
  has_visited_doctor: boolean;
  currently_taking_medicine: boolean;
  medication_details: string | null;
  sleep_status: string | null;
  appetite_status: string | null;
  bowel_status: string | null;
  tongue_description: string | null;
  medical_history: string | null;
  allergy_history: string | null;
  menstrual_history: string | null;
  profile_completed: boolean;
  summary: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface UserCaseProfilePayload {
  gender: string;
  age: number;
  chief_complaint: string;
  symptom_duration: string;
  primary_symptoms: string[];
  has_visited_doctor: boolean;
  currently_taking_medicine: boolean;
  medication_details?: string | null;
  sleep_status?: string | null;
  appetite_status?: string | null;
  bowel_status?: string | null;
  tongue_description?: string | null;
  medical_history?: string | null;
  allergy_history?: string | null;
  menstrual_history?: string | null;
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface RegisterRequest {
  username: string;
  email: string;
  password: string;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface ChatSession {
  session_id: string;
  title: string;
  summary: string | null;
  case_profile_id?: number | null;
  case_profile_name?: string | null;
  case_profile_summary?: string | null;
  created_at: string;
  updated_at: string;
}

export interface CaseProfile {
  id: number;
  user_id: number;
  profile_name: string;
  gender: string | null;
  age: number | null;
  height_cm: number | null;
  weight_kg: number | null;
  medical_history: string | null;
  allergy_history: string | null;
  current_medications: string | null;
  menstrual_history: string | null;
  notes: string | null;
  tags: string[];
  profile_completed: boolean;
  summary: string;
  created_at: string | null;
  updated_at: string | null;
}

export interface CaseProfilePayload {
  profile_name: string;
  gender?: string | null;
  age?: number | null;
  height_cm?: number | null;
  weight_kg?: number | null;
  medical_history?: string | null;
  allergy_history?: string | null;
  current_medications?: string | null;
  menstrual_history?: string | null;
  notes?: string | null;
  tags?: string[];
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  kind?: 'user' | 'answer' | 'followup';
  citations?: Citation[];
  latency_ms?: number;
  created_at: string;
}

export interface Citation {
  doc_id: string;
  doc_title: string;
  excerpt: string;
  chunk_id?: string;
  location?: string;
  /** @deprecated use excerpt instead */
  text?: string;
}

export interface UserLocationPayload {
  latitude: number;
  longitude: number;
  accuracy_m?: number;
  source?: string;
  label?: string;
  city?: string;
  province?: string;
}

export interface FeedbackData {
  message_id: number;
  feedback_type: 'like' | 'dislike' | 'correction' | 'badcase' | 'followup';
  content?: string;
}

export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
  trace_id: string;
}

// SSE event types
export interface SSEStartEvent {
  session_id: string;
  message_id: string;
}

export interface SSEChunkEvent {
  content: string;
}

export interface SSECitationEvent {
  citations: Citation[];
}

export interface SSEDoneEvent {
  total_tokens: number;
  latency_ms: number;
  message_id?: string;
  message_kind?: 'answer' | 'followup';
}

export interface SSEErrorEvent {
  code: string;
  message: string;
}
