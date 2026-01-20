import axios from "axios";
export const httpClient = axios.create({
    baseURL: process.env.YUNPAN_API_BASE ?? "http://bookapi.wowoziyuan.com",
    timeout: Number(process.env.HTTP_TIMEOUT_MS ?? 10000),
    headers: { "Content-Type": "application/json" }
});
