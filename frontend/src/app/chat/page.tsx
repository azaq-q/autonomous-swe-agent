"use client";

import { useState } from "react";

type Message = { role: "user" | "assistant"; content: string };

export default function Chat() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: "assistant",
      content: "你好，我是 Autonomous SWE Agent。请描述你的开发任务。",
    },
  ]);
  const [input, setInput] = useState("");

  function send() {
    const text = input.trim();
    if (!text) return;
    setMessages((m) => [...m, { role: "user", content: text }]);
    setInput("");
    // 流式响应（SSE）接入预留：后续对接后端 Agent 执行
    setMessages((m) => [
      ...m,
      { role: "assistant", content: "任务已接收，正在分析代码仓库..." },
    ]);
  }

  return (
    <main className="mx-auto flex max-w-5xl flex-col px-4 py-8" style={{ minHeight: "calc(100vh - 56px)" }}>
      <div className="flex-1 space-y-4">
        {messages.map((m, i) => (
          <div
            key={i}
            className={m.role === "user" ? "flex justify-end" : "flex justify-start"}
          >
            <div
              className={
                m.role === "user"
                  ? "max-w-[70%] rounded-lg bg-gray-900 px-4 py-2 text-sm text-white"
                  : "max-w-[70%] rounded-lg border border-gray-200 bg-white px-4 py-2 text-sm text-gray-800"
              }
            >
              {m.content}
            </div>
          </div>
        ))}
      </div>

      <div className="mt-6 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="描述你的任务，例如：Add OAuth login support with Google"
          className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm"
        />
        <button
          onClick={send}
          className="rounded-md bg-gray-900 px-4 py-2 text-sm text-white hover:bg-gray-700"
        >
          发送
        </button>
      </div>
    </main>
  );
}
