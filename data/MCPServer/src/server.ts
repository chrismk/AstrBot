#!/usr/bin/env node
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import { searchYunpan } from "./tools/searchYunpan.js";

const server = new Server(
  { name: "yunpan-mcp", version: "0.1.0" },
  { capabilities: { tools: {} } }
);

server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: "searchYunpan",
        description: "Search Yunpan resources and return the API's msg field",
        inputSchema: {
          type: "object",
          properties: {
            query: { type: "string", description: "Search keyword" }
          },
          required: ["query"]
        }
      }
    ]
  };
});

server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;
  if (name !== "searchYunpan") {
    throw new Error(`Unknown tool: ${name}`);
  }

  const query = String((args as Record<string, unknown>)?.query ?? "").trim();
  if (!query) {
    return { content: [{ type: "text", text: "query must not be empty" }] };
  }

  try {
    const result = await searchYunpan(query);
    const text = typeof result === "string" ? result : JSON.stringify(result);
    return { content: [{ type: "text", text }] };
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : String(error);
    return { content: [{ type: "text", text: `Error: ${message}` }] };
  }
});

const transport = new StdioServerTransport();
await server.connect(transport);


