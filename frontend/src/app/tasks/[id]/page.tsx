"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import {
  approveTask,
  BASE_URL,
  cancelTask,
  getTask,
  requestTaskChanges,
  type Task,
  type TaskEvent,
} from "@/lib/api";

const STATUS_ICON: Record<string, string> = {
  pending: "○",
  running: "●",
  done: "✓",
  failed: "✗",
};

export default function TaskTimeline() {
  const params = useParams();
  const [task, setTask] = useState<Task | null>(null);
  const [approving, setApproving] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [reworking, setReworking] = useState(false);
  const [feedback, setFeedback] = useState("");
  const [events, setEvents] = useState<TaskEvent[]>([]);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setInterval>;

    async function poll() {
      const t = await getTask(params.id as string);
      if (stopped) return;
      setTask(t);
      if (t && ["done", "failed", "cancelled"].includes(t.status)) {
        clearInterval(timer);
      }
    }

    poll();
    timer = setInterval(poll, 1000);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [params.id]);

  useEffect(() => {
    const source = new EventSource(`${BASE_URL}/api/v1/tasks/${params.id}/events/stream`);
    source.addEventListener("task_event", (message) => {
      const event = JSON.parse((message as MessageEvent).data) as TaskEvent;
      setEvents((current) => [...current.slice(-99), event]);
      getTask(params.id as string).then(setTask);
    });
    source.addEventListener("end", () => source.close());
    return () => source.close();
  }, [params.id]);

  if (!task) {
    return <main className="mx-auto max-w-5xl px-4 py-8">加载中...</main>;
  }

  return (
    <main className="mx-auto max-w-5xl px-4 py-8">
      <h1 className="text-xl font-bold text-gray-900">{task.prompt}</h1>
      <p className="mt-1 text-sm text-gray-500">任务 ID：{task.task_id} · 状态：{task.status}</p>
      <p className="mt-1 text-xs text-gray-400">
        执行尝试：{task.attempt} · 返工轮次：{task.revision}
      </p>
      <p className="mt-1 text-xs text-gray-400">
        Token：{task.input_tokens} in / {task.output_tokens} out · 预估成本：$
        {task.estimated_cost_usd.toFixed(4)}
      </p>
      {task.repository && <p className="mt-1 break-all text-sm text-gray-500">仓库：{task.repository}</p>}
      {task.base_commit && (
        <p className="mt-1 font-mono text-xs text-gray-500">
          {task.work_branch} @ {task.base_commit.slice(0, 12)}
        </p>
      )}
      {task.pr_url && (
        <a className="mt-2 block text-sm text-blue-700 underline" href={task.pr_url} target="_blank">
          查看 Pull Request #{task.pr_number}
        </a>
      )}

      <ol className="mt-8 space-y-4">
        {task.steps.map((step, i) => (
          <li key={i} className="flex items-center gap-3">
            <span className="text-lg">{STATUS_ICON[step.status] ?? "○"}</span>
            <span className="text-sm text-gray-700">{step.name}</span>
          </li>
        ))}
      </ol>

      {events.length > 0 && (
        <section className="mt-8">
          <h2 className="text-sm font-semibold text-gray-800">实时执行事件</h2>
          <ol className="mt-3 max-h-72 space-y-2 overflow-auto rounded-md bg-gray-50 p-3">
            {events.map((event) => (
              <li key={event.id} className="font-mono text-xs text-gray-600">
                {event.type} {JSON.stringify(event.payload)}
              </li>
            ))}
          </ol>
        </section>
      )}

      {task.status === "awaiting_approval" && (
        <div className="mt-8 rounded-lg border p-4">
          <textarea
            value={feedback}
            onChange={(event) => setFeedback(event.target.value)}
            placeholder="若需返工，请填写具体修改意见"
            className="min-h-24 w-full rounded-md border p-3 text-sm"
          />
          <div className="mt-3 flex gap-3">
            <button
              disabled={approving || reworking}
              onClick={async () => {
                setApproving(true);
                try {
                  setTask(await approveTask(task.task_id));
                } finally {
                  setApproving(false);
                }
              }}
              className="rounded-md bg-green-700 px-4 py-2 text-sm text-white disabled:opacity-50"
            >
              {approving ? "审批中..." : "批准结果"}
            </button>
            <button
              disabled={approving || reworking || feedback.trim().length < 3}
              onClick={async () => {
                setReworking(true);
                try {
                  setTask(await requestTaskChanges(task.task_id, feedback.trim()));
                  setFeedback("");
                } finally {
                  setReworking(false);
                }
              }}
              className="rounded-md border border-amber-400 px-4 py-2 text-sm text-amber-800 disabled:opacity-50"
            >
              {reworking ? "提交中..." : "要求返工"}
            </button>
          </div>
        </div>
      )}

      {!task.cancel_requested &&
        !["done", "failed", "cancelled", "awaiting_approval"].includes(task.status) && (
        <button
          disabled={cancelling}
          onClick={async () => {
            setCancelling(true);
            try {
              setTask(await cancelTask(task.task_id));
            } finally {
              setCancelling(false);
            }
          }}
          className="ml-3 mt-8 rounded-md border border-red-300 px-4 py-2 text-sm text-red-700 disabled:opacity-50"
        >
          {cancelling ? "取消中..." : "取消任务"}
        </button>
        )}

      {task.error && <pre className="mt-6 overflow-auto rounded bg-red-50 p-4 text-xs text-red-800">{task.error}</pre>}
      {Object.keys(task.result).length > 0 && (
        <pre className="mt-6 max-h-96 overflow-auto rounded bg-gray-950 p-4 text-xs text-gray-100">
          {JSON.stringify(task.result, null, 2)}
        </pre>
      )}
      {task.artifact_url && (
        <a
          className="mt-4 inline-block text-sm text-blue-700 underline"
          href={`${BASE_URL}${task.artifact_url}`}
          download
        >
          下载代码补丁（{task.artifact_sha256?.slice(0, 12)}）
        </a>
      )}
    </main>
  );
}
