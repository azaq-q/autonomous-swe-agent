"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { createTask, listTasks, type Task } from "@/lib/api";

export default function Dashboard() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [prompt, setPrompt] = useState("");

  useEffect(() => {
    listTasks().then(setTasks);
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!prompt.trim()) return;
    const task = await createTask(prompt.trim());
    setTasks((prev) => [task, ...prev]);
    setPrompt("");
  }

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <form onSubmit={handleCreate} className="mb-8 flex gap-2">
        <input
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="例如：修复登录后 Token 过期导致无法刷新"
          className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm"
        />
        <button
          type="submit"
          className="rounded-md bg-gray-900 px-4 py-2 text-sm text-white hover:bg-gray-700"
        >
          创建任务
        </button>
      </form>

      <div className="grid gap-3">
        {tasks.map((t) => (
          <Link
            key={t.task_id}
            href={`/tasks/${t.task_id}`}
            className="block rounded-md border border-gray-200 p-4 transition hover:bg-gray-50"
          >
            <div className="font-medium text-gray-900">{t.prompt}</div>
            <div className="mt-1 text-sm text-gray-500">状态：{t.status}</div>
          </Link>
        ))}
        {tasks.length === 0 && (
          <p className="text-sm text-gray-400">暂无任务，输入任务开始。</p>
        )}
      </div>
    </main>
  );
}
