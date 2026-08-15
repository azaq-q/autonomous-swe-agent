export type TaskStep = {
  name: string;
  status: "pending" | "running" | "done" | "failed";
};

export type Task = {
  task_id: string;
  prompt: string;
  repository?: string | null;
  status: string;
  steps: TaskStep[];
};

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

export async function listTasks(): Promise<Task[]> {
  try {
    const res = await fetch(`${BASE_URL}/api/v1/tasks`);
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

export async function createTask(prompt: string, repository?: string): Promise<Task> {
  const res = await fetch(`${BASE_URL}/api/v1/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, repository }),
  });
  if (!res.ok) throw new Error("创建任务失败");
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
