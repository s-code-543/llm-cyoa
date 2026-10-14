import { apiFetch } from "./client";

export type HomeData = {
  recent_games: {
    id: string;
    title: string;
    turn: number;
    max_turns: number;
    updated_at: string;
  }[];
  configurations: {
    id: number;
    name: string;
    description: string;
    prompt_name: string | null;
    total_turns: number;
    difficulty: string | null;
  }[];
};

export const getHome = () => apiFetch<HomeData>("/api/v1/home");
export const deleteGame = (id: string) =>
  apiFetch<{ deleted: boolean }>(`/api/v1/chat/conversations/${id}`, {
    method: "DELETE",
  });
