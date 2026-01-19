# WARP.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

AstrBot is a production-grade multi-platform LLM chatbot framework written in Python 3.10+ with a Vue.js dashboard. It's an Agent-based platform that seamlessly integrates with mainstream instant messaging platforms (QQ, Telegram, Discord, WeChat, Lark, DingTalk, Slack, etc.) and various LLM providers (OpenAI, Anthropic, Google Gemini, DeepSeek, Moonshot, etc.).

## Development Commands

### Environment Setup
```bash
# Install UV package manager (required)
pip install uv

# Install dependencies (takes 6-7 minutes)
uv sync

# Install pre-commit hooks for automatic code formatting
pip install pre-commit
pre-commit install
```

### Running the Application
```bash
# Run main application
uv run main.py

# Run with custom WebUI directory
uv run main.py --webui-dir /path/to/webui

# Run via CLI (alternative)
uv run astrbot run
```

The application starts on http://localhost:6185 with default credentials: `astrbot` / `astrbot`

### Dashboard (Vue.js)
```bash
cd dashboard

# Install dependencies (takes 2-3 minutes)
npm install

# Build for production (takes 25-30 seconds)
npm run build
```

The build output goes to `dashboard/dist/`

### Code Quality
```bash
# Check code style
uv run ruff check .

# Check formatting
uv run ruff format --check .

# Auto-fix formatting issues
uv run ruff format .
```

**ALWAYS run `uv run ruff check .` and `uv run ruff format .` before committing changes.**

### Testing
```bash
# Run all tests
uv run pytest

# Run specific test file
uv run pytest tests/test_main.py

# Run with coverage
uv run pytest --cov=astrbot
```

### Docker
```bash
# Build and run with Docker Compose
docker compose up -d

# Rebuild backend only (for local development)
./rebuild.sh
```

## Architecture

### Core Components

**Entry Point**: `main.py` → `InitialLoader` → `AstrBotCoreLifecycle`

**Component Initialization Order**:
1. Database (`db_helper`)
2. LogBroker (for centralized logging)
3. Configuration Manager (`AstrBotConfigManager`)
4. Persona Manager (character/personality system)
5. Provider Manager (LLM/STT/TTS providers)
6. Platform Manager (message platform adapters)
7. Knowledge Base Manager
8. Plugin Manager (Star system)
9. Pipeline Scheduler (message processing pipeline)
10. Event Bus (event routing and dispatching)

### Pipeline Architecture (Onion Model)

Messages flow through a multi-stage pipeline defined in `astrbot/core/pipeline/`:

1. **SessionStatusCheck**: Validates session state
2. **PreprocessStage**: Initial message preprocessing
3. **WakingStage**: Bot wake-up detection (at-mention, keywords, private chat)
4. **PluginStage**: Plugin event handlers execute here
5. **ProcessStage**: Main LLM processing (agent/STAR requests)
6. **ResultDecorateStage**: Response formatting and decoration
7. **RespondStage**: Send response to platform

Each stage can yield (pre-processing) → recursively process next stages → continue (post-processing). This enables middleware-like behavior with both pre and post hooks.

Key file: `astrbot/core/pipeline/scheduler.py`

### Platform Adapters

All platform-specific code lives in `astrbot/core/platform/sources/`. Each adapter implements:
- Message receiving and parsing
- Message sending with platform-specific features (buttons, embeds, etc.)
- Event type conversion to unified `AstrMessageEvent`

Common base: `AstrMessageEvent` in `astrbot/core/platform/astr_message_event.py`

### Provider System

Located in `astrbot/core/provider/`, supports:
- **Provider Types**: ChatCompletion, STT (Speech-to-Text), TTS (Text-to-Speech), Embedding, Rerank
- **Registration**: Providers register via `provider_cls_map` in `astrbot/core/provider/register.py`
- **Session Isolation**: Per-user provider selection via `umo` (unified message origin)
- **Tool Support**: LLM function calling via `func_tool_manager.py`

Key file: `astrbot/core/provider/manager.py`

### Plugin System (Star)

Plugins extend functionality via event handlers and tools. Located in:
- Built-in plugins: `packages/`
- User plugins: `data/plugins/`

**Plugin Structure**:
```
plugin_name/
├── main.py              # Plugin class with @filter.command decorators
├── metadata.yaml        # Plugin metadata
└── handlers/           # Optional: modular handlers
```

**Key Patterns**:
- Use `@filter.command("cmd")` for command handlers
- Call `event.stop_event()` to prevent event propagation
- Access context via `self.context` (includes db, provider_manager, platform_manager, etc.)
- Use common utilities from `data/plugins/common/` for cross-platform compatibility

**Important Files**:
- Plugin standard: `docs/README_插件开发标准.md`
- Architecture review: `docs/ARCHITECTURE_REVIEW.md`
- Common utilities: `data/plugins/common/README.md`

### Database

Uses SQLAlchemy with async support (aiosqlite). Database helpers in `astrbot/core/db/`.

Important tables:
- `Conversation`: Chat history
- `PlatformMessageHistory`: Platform-specific message tracking
- `KnowledgeBase`: Vector store for knowledge retrieval

### Configuration

Centralized in `astrbot/core/config/default.py` with UMOP (Unified Message Origin Preference) support for per-user/per-group overrides.

Config files stored in: `data/config/`

### Knowledge Base (RAG)

Vector-based retrieval system in `astrbot/core/knowledge_base/`:
- Uses FAISS for vector storage
- Supports multiple embedding providers
- BM25 + semantic hybrid search
- Document parsing via markitdown

## Key Conventions

### Message Components

All messages use a component-based system (`astrbot/core/message/components.py`):
- `Plain`: Text
- `Image`: Images with URL/path/file/base64
- `At`: Mention user
- `Reply`: Quote reply
- `Face`: Emoji/stickers

Construct responses using `MessageChain`:
```python
from astrbot.core.message.components import Plain, Image
from astrbot.core.message.message_event_result import MessageChain

yield event.plain_result("text")  # Shorthand
# or
yield MessageChain([Plain("Hello"), Image(url="https://...")])
```

### Event Lifecycle

1. Platform adapter receives raw message
2. Converts to `AstrMessageEvent`
3. Pushes to event queue
4. EventBus routes to pipeline
5. Pipeline stages process (onion model)
6. Response sent via platform adapter

### Session Management

Sessions tracked via `session_id` (format: `platform:type:user_or_group_id`):
- Use `event.unified_msg_origin` for consistent session keys
- Store session data via `astrbot.api.sp` (shared persistence)
- Access via `sp.get(key, default, scope="umo", scope_id=event.unified_msg_origin)`

### Tool/Function Calling

Register tools via plugin decorators:
```python
from astrbot.api import filter

@filter.llm_tool(
    name="tool_name",
    description="What this tool does"
)
async def my_tool(param1: str) -> str:
    """Tool implementation"""
    return result
```

Tools automatically available to LLMs that support function calling.

## Common Patterns

### Cross-Platform Button/Session Handling

Use platform capability detection:
```python
from data.plugins.common import get_platform_capabilities

capabilities = get_platform_capabilities(event, "YourPlugin")
if capabilities['supports_buttons']:
    # Use inline keyboard (Telegram, Discord)
    keyboard = create_inline_keyboard(...)
else:
    # Use session-based menu (Lark, WeChat, QQ)
    session_manager.create_session(...)
```

### Accessing Services

Via plugin context:
```python
self.context.db_helper  # Database
self.context.provider_manager  # LLM providers
self.context.platform_manager  # Platform adapters
self.context.conversation_manager  # Chat history
self.context.persona_mgr  # Personalities
self.context.kb_manager  # Knowledge base
```

### Logging

Use the centralized logger:
```python
from astrbot import logger

logger.info("message")
logger.debug("debug info")
logger.error("error", exc_info=True)
```

## Important Notes

### Python Version
Requires Python 3.10+. Check `.python-version` file.

### UV Package Manager
This project uses `uv` for fast, reliable dependency management. Do NOT use `pip install -r requirements.txt` directly. Always use `uv sync`.

### Pre-commit Hooks
Ruff formatting is enforced via pre-commit hooks. Changes that don't pass formatting will be auto-rejected.

### Testing Considerations
When running tests with `uv run pytest`, tests automatically add project root to sys.path. Some tests mock external dependencies.

### Dashboard Download
On first run, AstrBot downloads the WebUI from GitHub releases. If this fails (known "division by zero" error), the application still works—just access via the dashboard route.

### Multi-Language
Project supports Chinese (primary), English, and Japanese. UI strings use i18n.

### Docker Deployment
Primary deployment method. Exposes multiple ports:
- 6185: WebUI
- 6195: WeChat
- 6199: QQ

Mount `./data` directory for persistence.

### Code Style
- Line length: 88 characters (Black-compatible)
- Target: Python 3.10+
- Enforced rules: Pyflakes, pycodestyle, flake8-async, import-order, pyupgrade
- Ignored: F403, F405, E501, ASYNC230

## Repository Structure

```
AstrBot/
├── main.py                     # Application entry point
├── astrbot/                    # Core framework
│   ├── api/                   # Public plugin API
│   ├── cli/                   # CLI commands
│   ├── core/                  # Core components
│   │   ├── agent/            # Agent/LLM runners (Coze, Dify, etc.)
│   │   ├── config/           # Configuration system
│   │   ├── db/               # Database layer
│   │   ├── knowledge_base/   # RAG system
│   │   ├── pipeline/         # Message processing pipeline
│   │   ├── platform/         # Platform adapters
│   │   ├── provider/         # LLM/STT/TTS providers
│   │   ├── star/             # Plugin system
│   │   └── utils/            # Utility functions
│   └── dashboard/            # Backend API for WebUI
├── dashboard/                 # Vue.js frontend (separate build)
├── data/                     # Runtime data (gitignored)
│   ├── config/              # User configurations
│   ├── plugins/             # User-installed plugins
│   └── temp/                # Temporary files
├── packages/                 # Built-in plugins
├── tests/                    # Test suite
└── docs/                     # Documentation (Chinese)
```

## Additional Resources

- Plugin Development Standard: `docs/README_插件开发标准.md`
- Architecture Review: `docs/ARCHITECTURE_REVIEW.md`
- GitHub Copilot Instructions: `.github/copilot-instructions.md`
