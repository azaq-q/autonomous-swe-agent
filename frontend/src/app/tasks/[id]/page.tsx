"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { getTask, type Task } from "@/lib/api";

const STATUS_ICON: Record<string, string> = {
  pending: "○",
  running: "●",
  done: "✓",
  failed: "✗",
};

export default function TaskTimeline() {
  const params = useParams();
  const [task, setTask] = useState<Task | null>(null);

  useEffect(() => {
    getTask(params.id as string).then(setTask);
  }, [params.id]);

  if (!task) {
    return <main className="mx-auto max-w-5xl px-4 py-8">加载中...</main>;
  }

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <h1 className="text-xl font-bold text-gray-900">{task.prompt}</h1>
      <p className="mt-1 text-sm text-gray-500">任务 ID：{task.task_id} · 状态：{task.status}</p>

      <ol className="mt-8 space-y-4">
        {task.steps.map((step, i) => (
          <li key={i} className="flex items-center gap-3">
            <span className="text-lg">{STATUS_ICON[step.status] ?? "○"}</span>
            <span className="text-sm text-gray-700">{step.name}</span>
          </li>
        ))}
      </ol>
    </main>
  );
}
