"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { createTask, listTasks, type Task } from "@/lib/api";

export default function Dashboard() {
  const router = useRouter();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [prompt, setPrompt] = useState("");
  const [repository, setRepository] = useState("");
  const [testCommand, setTestCommand] = useState("pytest");

  useEffect(() => {
    listTasks().then(setTasks);
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!prompt.trim()) return;
    const task = await createTask({
      prompt: prompt.trim(),
      repository: repository.trim() || undefined,
      test_command: testCommand.trim(),
    });
    setTasks((prev) => [task, ...prev]);
    setPrompt("");
    router.push(`/tasks/${task.task_id}`);
  }

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <form onSubmit={handleCreate} className="mb-8 grid gap-3 rounded-lg border p-4">
        <input
          value={repository}
          onChange={(e) => setRepository(e.target.value)}
          placeholder="Git 仓库 URL（可选）"
          className="rounded-md border border-gray-300 px-3 py-2 text-sm"
        />
        <input
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="例如：修复登录后 Token 过期导致无法刷新"
          className="rounded-md border border-gray-300 px-3 py-2 text-sm"
        />
        <input
          value={testCommand}
          onChange={(e) => setTestCommand(e.target.value)}
          placeholder="测试命令，例如 pytest -q"
          className="rounded-md border border-gray-300 px-3 py-2 text-sm"
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
            {t.repository && <div className="mt-1 truncate text-xs text-gray-400">{t.repository}</div>}
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
