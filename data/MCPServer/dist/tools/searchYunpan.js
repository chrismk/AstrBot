import { httpClient } from "../lib/http.js";
export async function searchYunpan(query) {
    const trimmedQuery = (query ?? "").trim();
    if (!trimmedQuery) {
        throw new Error("query must not be empty");
    }
    const { data } = await httpClient.post("/api/search_yunpan", {
        cmd: trimmedQuery,
        platform: "fwh",
        user_id: 0,
        chat_id: 0,
        message_id: 0
    });
    // 返回 response.msg 按你的要求
    // 若未提供 msg，则返回原始 data
    // 交给上层将其转为文本或结构化内容
    // eslint-disable-next-line @typescript-eslint/no-unsafe-return
    return data?.msg ?? data;
}
