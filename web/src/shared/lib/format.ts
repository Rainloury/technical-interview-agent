const dateFormatter = new Intl.DateTimeFormat("zh-CN", {
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

export function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "时间未知" : dateFormatter.format(date);
}

export const taskTypeLabels = {
  resume: "简历",
  qa: "问答",
  interview: "面试",
  wrong_question: "错题",
} as const;

export const taskStateLabels: Record<string, string> = {
  uploaded: "已上传",
  extracting: "提取中",
  analyzing: "分析中",
  generating_questions: "生成题目中",
  completed: "已完成",
  failed: "未完成",
  source_deleted: "来源已删除",
  created: "已创建",
  retrieving: "检索中",
  answering: "回答中",
  in_progress: "进行中",
  ended: "已结束",
  scoring: "评分中",
  branch_completed: "分支已结束",
};

export function stateLabel(state: string): string {
  return taskStateLabels[state] ?? "状态更新中";
}
