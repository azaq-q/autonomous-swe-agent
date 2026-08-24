export type TaskStep = {
  name: string;
  status: "pending" | "running" | "done" | "failed";
};

export type Task = {
  task_id: string;
  prompt: string;
  repository?: string | null;
  base_branch: string;
  source_commit?: string | null;
  test_command: string;
  max_iterations: number;
  experiment_variant: "full" | "single_agent" | "no_rag" | "no_review";
  status: string;
  steps: TaskStep[];
  result: Record<string, unknown>;
  error?: string | null;
  base_commit?: string | null;
  work_branch?: string | null;
  artifact_sha256?: string | null;
  artifact_url?: string | null;
  attempt: number;
  cancel_requested: boolean;
  revision: number;
  published_commit?: string | null;
  pr_url?: string | null;
  pr_number?: number | null;
  input_tokens: number;
  output_tokens: number;
  estimated_cost_usd: number;
};

export type TaskEvent = {
  id: number;
  type: string;
  payload: Record<string, unknown>;
  created_at: string;
};

export type CreateTaskInput = {
  prompt: string;
  repository?: string;
  base_branch?: string;
  source_commit?: string;
  test_command?: string;
  max_iterations?: number;
  experiment_variant?: "full" | "single_agent" | "no_rag" | "no_review";
};

export const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export async function listTasks(): Promise<Task[]> {
  try {
    const res = await fetch(`${BASE_URL}/api/v1/tasks`);
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

export async function createTask(input: CreateTaskInput): Promise<Task> {
  const res = await fetch(`${BASE_URL}/api/v1/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!res.ok) throw new Error("创建任务失败");
  return await res.json();
}

export async function approveTask(taskId: string): Promise<Task> {
  const res = await fetch(`${BASE_URL}/api/v1/tasks/${taskId}/approve`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("审批任务失败");
  return await res.json();
}

export async function cancelTask(taskId: string): Promise<Task> {
  const res = await fetch(`${BASE_URL}/api/v1/tasks/${taskId}/cancel`, {
    method: "POST",
  });
  if (!res.ok) throw new Error("取消任务失败");
  return await res.json();
}

export async function requestTaskChanges(taskId: string, feedback: string): Promise<Task> {
  const res = await fetch(`${BASE_URL}/api/v1/tasks/${taskId}/request-changes`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ feedback }),
  });
  if (!res.ok) throw new Error("提交返工意见失败");
  return await res.json();
}

export async function getTask(taskId: string): Promise<Task | null> {
  try {
    const res = await fetch(`${BASE_URL}/api/v1/tasks/${taskId}`);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}
