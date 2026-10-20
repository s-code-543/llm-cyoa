import { apiFetch } from "./client";

export type AuditSummary = {
  id: number;
  timestamp: string;
  was_modified: boolean;
  was_refusal: boolean;
  preview: string;
};
export type AuditDetail = AuditSummary & {
  original_text: string;
  refined_text: string;
  classifier_response: string;
  prompt_used: string | null;
  correction_prompt_used: string | null;
  details: unknown;
};
export type Dashboard = {
  total_requests: number;
  total_refusals: number;
  total_corrections: number;
  correction_rate: number;
  recent: AuditSummary[];
};
export type PromptSummary = {
  id: number;
  type: string;
  name: string;
  version: number;
  description: string;
};
export type PromptDetail = PromptSummary & {
  prompt_text: string;
  file_path: string;
  versions: { id: number; version: number; description: string }[];
};
export type PromptList = {
  types: { value: string; label: string }[];
  prompts: PromptSummary[];
};
export type PromptInput = { description: string; prompt_text: string };

const base = "/api/v1/admin";

export const getDashboard = () => apiFetch<Dashboard>(`${base}/dashboard`);
export const getAudit = (modifiedOnly: boolean) =>
  apiFetch<{ logs: AuditSummary[] }>(
    `${base}/audit${modifiedOnly ? "?modified_only=true" : ""}`,
  );
export const getAuditEntry = (id: number) =>
  apiFetch<AuditDetail>(`${base}/audit/${id}`);
export const clearAudit = () =>
  apiFetch<{ deleted: number }>(`${base}/audit`, { method: "DELETE" });

export const getPrompts = () => apiFetch<PromptList>(`${base}/prompts`);
export const getPrompt = (id: number) =>
  apiFetch<PromptDetail>(`${base}/prompts/${id}`);
export const createPrompt = (
  payload: PromptInput & { type: string; name: string },
) => apiFetch<PromptDetail>(`${base}/prompts`, { payload });
export const updatePrompt = (id: number, payload: PromptInput) =>
  apiFetch<PromptDetail>(`${base}/prompts/${id}`, { method: "PUT", payload });
export const createPromptVersion = (id: number, payload: PromptInput) =>
  apiFetch<PromptDetail>(`${base}/prompts/${id}/versions`, { payload });
export const savePromptToDisk = (id: number) =>
  apiFetch<{ message: string; prompt: PromptDetail }>(
    `${base}/prompts/${id}/save-to-disk`,
    { method: "POST", payload: {} },
  );

export type Provider = {
  id: number;
  name: string;
  provider_type: string;
  base_url: string;
  has_api_key: boolean;
  api_key_hint: string;
  is_active: boolean;
  last_tested: string | null;
  test_status: string;
  model_count: number;
};
export type ProviderInput = {
  name: string;
  provider_type: string;
  base_url: string;
  api_key?: string;
  clear_api_key?: boolean;
};
export type ModelPricing = Record<string, unknown>;
export type ModelMetadata = {
  pricing_source?: string | null;
  pricing_note?: string | null;
  pricing_updated_at?: string | null;
  context_length?: number;
  created?: number | null;
  architecture?: { input_modalities?: string[]; output_modalities?: string[]; tokenizer?: string };
  supported_parameters?: string[] | Record<string, unknown>;
};
export type ModelRow = ModelMetadata & {
  pricing?: ModelPricing;
  pricing_updated_at?: string | null;
  image_generation?: boolean;
  id: number;
  name: string;
  model_identifier: string;
  provider_id: number;
  provider_name: string;
  provider_type: string;
  is_available: boolean;
  description: string;
};
export type RemoteModel = ModelMetadata & {
  pricing?: ModelPricing;
  image_generation?: boolean;
  id: string;
  name: string;
  description: string;
  size: number;
  imported: boolean;
};
export type Difficulty = {
  id: number;
  name: string;
  description: string;
  function: string;
  curve_points: number[] | null;
};
export type DifficultyInput = {
  name: string;
  description: string;
  curve_points?: number[];
  function?: string;
};
export type Tts = {
  enabled: boolean;
  openai_model: string;
  openai_voice: string;
  max_text_length: number;
  audio_retention_days: number;
  auto_cleanup_enabled: boolean;
  model_choices: { value: string; label: string }[];
  voice_choices: { value: string; label: string }[];
};
export type Message = { message: string };

export const getProviders = () =>
  apiFetch<{ types: { value: string; label: string }[]; providers: Provider[] }>(`${base}/providers`);
export const createProvider = (payload: ProviderInput) =>
  apiFetch<Provider>(`${base}/providers`, { payload });
export const updateProvider = (id: number, payload: Partial<ProviderInput>) =>
  apiFetch<Provider>(`${base}/providers/${id}`, { method: "PUT", payload });
export const deleteProvider = (id: number) =>
  apiFetch<{ deleted: boolean }>(`${base}/providers/${id}`, { method: "DELETE" });
export const testProvider = (payload: {
  provider_id?: number;
  provider_type: string;
  base_url: string;
  api_key?: string;
}) => apiFetch<{ success: boolean; message: string }>(`${base}/providers/test`, { payload });
export const browseModels = (id: number) =>
  apiFetch<{ provider: Provider; models: RemoteModel[]; pricing_warnings?: string[] }>(`${base}/providers/${id}/models`);
export const importModels = (id: number, model_ids: string[]) =>
  apiFetch<Message>(`${base}/providers/${id}/models/import`, { payload: { model_ids } });
export const removeModels = (id: number, model_ids: string[]) =>
  apiFetch<Message>(`${base}/providers/${id}/models/remove`, { payload: { model_ids } });
export const syncModels = (id: number) =>
  apiFetch<Message>(`${base}/providers/${id}/models/sync`, { payload: {} });

export const getModels = () =>
  apiFetch<{ models: ModelRow[]; providers: { id: number; name: string }[] }>(`${base}/models`);
export const deleteModel = (id: number) =>
  apiFetch<{ deleted: boolean }>(`${base}/models/${id}`, { method: "DELETE" });

export const getDifficulties = () => apiFetch<{ profiles: Difficulty[] }>(`${base}/difficulty`);
export const createDifficulty = (payload: DifficultyInput) =>
  apiFetch<Difficulty>(`${base}/difficulty`, { payload });
export const updateDifficulty = (id: number, payload: DifficultyInput) =>
  apiFetch<Difficulty>(`${base}/difficulty/${id}`, { method: "PUT", payload });
export const deleteDifficulty = (id: number) =>
  apiFetch<{ deleted: boolean }>(`${base}/difficulty/${id}`, { method: "DELETE" });

export const getTts = () => apiFetch<Tts>(`${base}/tts`);
export const updateTts = (payload: Partial<Tts>) =>
  apiFetch<Tts>(`${base}/tts`, { method: "PUT", payload });

export type JudgeStepData = {
  id?: number;
  name: string;
  enabled: boolean;
  classifier_prompt: number | null;
  classifier_model: number | null;
  classifier_timeout: number;
  classifier_question: string;
  classifier_use_full_context: boolean;
  rewrite_prompt: number | null;
  rewrite_model: number | null;
  rewrite_timeout: number;
  rewrite_instruction: string;
  rewrite_use_full_context: boolean;
  max_rewrite_attempts: number;
  compare_prompt: number | null;
  compare_model: number | null;
  compare_timeout: number;
  compare_question: string;
  compare_use_full_context: boolean;
};
export type WorkflowNode = { type: string; [key: string]: unknown };
export type Workflow = { version?: number; nodes?: WorkflowNode[] };
export type ConfigData = {
  is_active?: boolean;
  in_progress_count?: number;
  id?: number;
  name: string;
  description: string;
  adventure_prompt: number | null;
  storyteller_model: number | null;
  storyteller_timeout: number;
  game_ending_prompt: number | null;
  game_ending_turn_correction_prompt: number | null;
  difficulty: number | null;
  total_turns: number;
  phase1_turns: number;
  phase2_turns: number;
  phase3_turns: number;
  phase4_turns: number;
  enable_tts: boolean;
  enable_image_generation: boolean;
  image_meta_prompt: number | null;
  character_prompt: number | null;
  image_model: number | null;
  image_aspect_ratio: string;
  image_timeout: number;
  enable_refusal_detection: boolean;
  turn_correction_prompt: number | null;
  turn_correction_model: number | null;
  turn_correction_timeout: number;
  classifier_prompt: number | null;
  classifier_model: number | null;
  classifier_timeout: number;
  classifier_question: string;
  workflow: Workflow;
  judge_steps: JudgeStepData[];
};
export type ConfigSummary = {
  is_active: boolean;
  in_progress_count: number;
  id: number;
  name: string;
  description: string;
  storyteller_model: string;
  total_turns: number;
  enable_refusal_detection: boolean;
  enable_tts: boolean;
  enable_image_generation: boolean;
  judge_step_count: number;
};
export type ConfigOptions = {
  adventure_prompts: PromptSummary[];
  turn_correction_prompts: PromptSummary[];
  game_ending_prompts: PromptSummary[];
  classifier_prompts: PromptSummary[];
  judge_prompts: PromptSummary[];
  character_prompts: PromptSummary[];
  image_meta_prompts: PromptSummary[];
  image_models: { id: number; name: string; available: boolean }[];
  models: { id: number; name: string; available: boolean }[];
  difficulties: { id: number; name: string }[];
};

export const getConfigs = () =>
  apiFetch<{ configurations: ConfigSummary[] }>(`${base}/configurations`);
export const getConfigOptions = () => apiFetch<ConfigOptions>(`${base}/configurations/options`);
export const getConfig = (id: number) => apiFetch<ConfigData>(`${base}/configurations/${id}`);
export const createConfig = (payload: ConfigData) =>
  apiFetch<ConfigData>(`${base}/configurations`, { payload });
export const updateConfig = (id: number, payload: ConfigData) =>
  apiFetch<ConfigData>(`${base}/configurations/${id}`, { method: "PUT", payload });
export const deleteConfig = (id: number) =>
  apiFetch<{ deleted: boolean }>(`${base}/configurations/${id}`, { method: "DELETE" });

export const validateModels = () =>
  apiFetch<{ unavailable: ModelRow[]; failures: string[] }>(
    `${base}/models/validate`,
    { payload: {} },
  );
export const deleteUnavailableModels = (delete_ids: number[]) =>
  apiFetch<Message>(`${base}/models/validate`, { payload: { delete_ids } });

export type AdminChat = { id: string; title: string; owner: string; updated_at: string };
export const getAdminChats = (search: string, offset: number) =>
  apiFetch<{ chats: AdminChat[]; has_more: boolean }>(`${base}/chats?${new URLSearchParams({ search, offset: String(offset) })}`);

export const refreshModelCosts = () =>
  apiFetch<Message & { failures: string[] }>(`${base}/models/pricing/refresh`, { payload: {} });
