import axios from "axios";
import { httpClient } from "../lib/http.js";

const DISK_API_URL = "https://so.zslren.com/open/search/disk?token=5GLynslKVhw486iJvPKh";

function isBlank(value: unknown): boolean {
  return typeof value === "string" ? value.trim().length === 0 : value == null;
}

function cleanHighlight(input: string): string {
  return input
    .replaceAll("\\u003cem\\u003e", "")
    .replaceAll("\\u003c/em\\u003e", "")
    .replaceAll("<em>", "")
    .replaceAll("</em>", "");
}

function formatDiskResults(data: any): string {
  try {
    if (!data || data.code !== 200) return "";
    const list = data?.data?.list ?? [];
    if (!Array.isArray(list) || list.length === 0) return "";
    const lines: string[] = [];
    for (const item of list.slice(0, 15)) {
      const rawName = String(item?.disk_name ?? "");
      const name = cleanHighlight(rawName);
      const link = String(item?.link ?? "");
      lines.push(`${name}\n${link}`);
    }
    return lines.join("\n\n").trim();
  } catch {
    return "";
  }
}

export async function searchYunpan(query: string): Promise<string> {
  const trimmedQuery = (query ?? "").trim();
  if (!trimmedQuery) {
    throw new Error("query must not be empty");
  }

  // 1) 优先调用旧接口
  try {
    const { data } = await httpClient.post("/api/search_yunpan", {
      cmd: trimmedQuery,
      platform: "fwh",
      user_id: 0,
      chat_id: 0,
      message_id: 0
    }, { headers: { "Accept": "application/json, text/plain, */*" }, timeout: 10000 });

    const msg = (data as any)?.msg;
    if (!isBlank(msg)) {
      const msgStr = typeof msg === "string" ? msg : JSON.stringify(msg);
      // 若提示“暂无此资源”，转而调用 search disk 作为兜底
      if (msgStr.includes("暂无此资源") || msgStr.trim().length === 0) {
        // fall through to disk api below
      } else {
        return msgStr;
      }
    }
  } catch (e) {
    // 忽略错误，尝试备用接口
  }

  // 2) 备用：search disk 接口
  try {
    const { data } = await axios.post(
      DISK_API_URL,
      {
        q: trimmedQuery,
        type: "",
        exact: true,
        user: "",
        share_time: "",
        format: [],
        page: 1,
        size: 15
      },
      { headers: { "Content-Type": "application/json", "Accept": "application/json, text/plain, */*" }, timeout: 15000 }
    );
    const formatted = formatDiskResults(data);
    if (!isBlank(formatted)) return formatted;
    return typeof data === "string" ? data : JSON.stringify(data);
  } catch (e) {
    // 两个接口都失败
    const message = e instanceof Error ? e.message : String(e);
    return `Error: ${message}`;
  }
}


