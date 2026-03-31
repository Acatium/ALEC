import { useState } from "react";
import {
  useQuestions,
  useCreateQuestion,
  useUpdateQuestion,
  useDeleteQuestion,
} from "../api/hooks";

interface Props {
  engagementId: string;
}

export default function QuestionsPanel({ engagementId }: Props) {
  const { data: questions } = useQuestions(engagementId);
  const createQuestion = useCreateQuestion();
  const updateQuestion = useUpdateQuestion();
  const deleteQuestion = useDeleteQuestion();

  const [text, setText] = useState("");

  const handleAsk = () => {
    const trimmed = text.trim();
    if (!trimmed) return;
    createQuestion.mutate(
      { engagementId, question_text: trimmed },
      { onSuccess: () => setText("") },
    );
  };

  const openCount = questions?.filter((q) => q.status === "open").length ?? 0;

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <h3 className="mb-3 text-sm font-medium text-gray-700">
        Questions{" "}
        {openCount > 0 && (
          <span className="ml-1 rounded-full bg-indigo-100 px-1.5 py-0.5 text-[10px] font-medium text-indigo-600">
            {openCount} open
          </span>
        )}
      </h3>

      {/* Ask input */}
      <div className="mb-3 flex gap-2">
        <input
          type="text"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && handleAsk()}
          placeholder="Ask a question..."
          className="flex-1 rounded border border-gray-200 px-2 py-1 text-xs text-gray-700 placeholder-gray-400 focus:border-indigo-300 focus:outline-none"
        />
        <button
          onClick={handleAsk}
          disabled={createQuestion.isPending || !text.trim()}
          className="rounded bg-indigo-600 px-2 py-1 text-xs text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          Ask
        </button>
      </div>

      {/* Question list */}
      <div className="space-y-2 max-h-64 overflow-y-auto">
        {questions?.map((q) => (
          <div
            key={q.question_id}
            className={`rounded border p-2 ${
              q.status === "answered"
                ? "border-green-200 bg-green-50"
                : q.status === "dismissed"
                  ? "border-gray-100 bg-gray-50 opacity-60"
                  : "border-gray-200"
            }`}
          >
            <p className="text-xs text-gray-700">{q.question_text}</p>

            {q.status === "answered" && q.answer && (
              <p className="mt-1 text-xs text-green-700">{q.answer}</p>
            )}

            <div className="mt-1 flex items-center gap-2">
              <span className="text-[10px] text-gray-400">
                {new Date(q.created_at).toLocaleDateString()}
              </span>
              {q.status === "open" && (
                <button
                  onClick={() =>
                    updateQuestion.mutate({
                      engagementId,
                      questionId: q.question_id,
                      data: { status: "dismissed" },
                    })
                  }
                  className="text-[10px] text-gray-400 hover:text-gray-600"
                >
                  Dismiss
                </button>
              )}
              {q.status === "dismissed" && (
                <button
                  onClick={() =>
                    updateQuestion.mutate({
                      engagementId,
                      questionId: q.question_id,
                      data: { status: "open" },
                    })
                  }
                  className="text-[10px] text-indigo-500 hover:text-indigo-700"
                >
                  Reopen
                </button>
              )}
              {q.status === "answered" && (
                <button
                  onClick={() =>
                    updateQuestion.mutate({
                      engagementId,
                      questionId: q.question_id,
                      data: { status: "open" },
                    })
                  }
                  className="text-[10px] text-indigo-500 hover:text-indigo-700"
                >
                  Reopen
                </button>
              )}
              <button
                onClick={() =>
                  deleteQuestion.mutate({
                    engagementId,
                    questionId: q.question_id,
                  })
                }
                className="text-[10px] text-red-400 hover:text-red-600"
              >
                Delete
              </button>
            </div>
          </div>
        ))}
        {(!questions || questions.length === 0) && (
          <p className="text-xs text-gray-400">No questions yet</p>
        )}
      </div>
    </div>
  );
}
