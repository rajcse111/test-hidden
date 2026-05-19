\# AI Answer Assistant Overlay Desktop Application

\## Production Grade Requirements Document



\---



\# 1. Project Overview



Build a production-grade desktop AI assistant application similar to InterviewHelpAI.



The application should provide:



1\. A floating invisible/overlay desktop assistant

2\. Real-time microphone + system audio listening

3\. Real-time speech-to-text transcription

4\. Real-time AI-generated interview assistance

5\. Streaming responses

6\. Optional screen/context analysis

7\. Local-first architecture support

8\. Production deployment readiness



The app must support:

\- Windows (primary target)

\- macOS (secondary)

\- Linux (optional)



\---



\# 2. High-Level Architecture



System architecture:



Electron Desktop App

&#x20;   |

&#x20;   |-- Overlay UI (React)

&#x20;   |-- Audio Capture Layer

&#x20;   |-- Screenshot Capture Layer

&#x20;   |-- WebSocket Client

&#x20;   |

FastAPI Backend

&#x20;   |

&#x20;   |-- Whisper STT Service

&#x20;   |-- LLM Orchestrator

&#x20;   |-- Prompt Builder

&#x20;   |-- Streaming Engine

&#x20;   |-- OCR Service

&#x20;   |

LLM Provider

&#x20;   |-- OpenAI

&#x20;   |-- Gemini

&#x20;   |-- Ollama (local)

&#x20;   |-- OpenRouter support



\---



\# 3. Tech Stack



\## Frontend/Desktop



\- Electron

\- React

\- TypeScript

\- TailwindCSS

\- Zustand (state management)

\- Framer Motion

\- Vite



\## Backend



\- Python 3.11+

\- FastAPI

\- WebSockets

\- Uvicorn

\- Pydantic

\- AsyncIO



\## AI



\- OpenAI SDK

\- Gemini SDK

\- Ollama support

\- LangChain optional



\## STT



\- faster-whisper



\## OCR



\- Tesseract OCR

\- Optional GPT Vision support



\## Packaging



\- Electron Builder



\## Logging



\- Winston (frontend)

\- Loguru (backend)



\## Testing



\- Playwright

\- Pytest

\- Vitest



\---



\# 4. Desktop Overlay Requirements



\## Overlay Window



The desktop application must support:



\- Frameless window

\- Transparent background

\- Always-on-top

\- Click-through mode

\- Toggle visibility

\- Global hotkeys

\- Draggable compact widget

\- Multi-monitor support



\## Overlay Modes



\### Mode 1: Hidden Passive Listening

\- Small floating indicator

\- Shows recording state

\- Minimal footprint



\### Mode 2: Expanded Assistant

Tabs:

\- Live Transcript

\- AI Analysis

\- Suggested Answers

\- Notes



\### Mode 3: Fully Invisible

\- No taskbar icon

\- Transparent

\- Keyboard shortcut only



\## Electron Requirements



Use:

\- BrowserWindow

\- setAlwaysOnTop

\- setIgnoreMouseEvents

\- transparent windows

\- IPC communication



Global shortcuts:

\- Toggle overlay

\- Start/stop listening

\- Push-to-talk

\- Screenshot capture



\---



\# 5. Audio Capture Requirements



\## Inputs



Support:

\- Microphone audio

\- System audio

\- Simultaneous capture



\## Audio Features



\- Noise suppression

\- Echo cancellation

\- Chunked streaming

\- Low latency

\- Real-time processing



\## Platform Notes



\### Windows

\- WASAPI loopback



\### macOS

\- BlackHole support



\### Linux

\- PulseAudio support



\## Audio Streaming



Audio chunks:

\- 1-2 seconds max

\- PCM format

\- Streamed via WebSocket



\---



\# 6. Speech-to-Text Requirements



\## Engine



Use:

\- faster-whisper



\## Requirements



\- Streaming transcription

\- Partial transcript updates

\- Speaker segmentation optional

\- Timestamp support

\- Multi-language optional



\## Models



Configurable:

\- tiny

\- base

\- medium

\- large-v3



\## Performance



Target:

\- <1.5 second latency



\---



\# 7. AI Backend Requirements



\## Backend Framework



Use FastAPI.



\## Backend Responsibilities



\- Receive transcripts

\- Maintain conversation context

\- Build prompts

\- Call LLMs

\- Stream responses

\- Handle OCR context

\- Session management



\## LLM Providers



Support:

\- OpenAI

\- Gemini

\- Ollama

\- OpenRouter



\## Model Configurations



Configurable:

\- GPT-4.1

\- GPT-4o

\- Gemini 2.5

\- DeepSeek

\- Llama 3

\- Qwen



\## Prompt Modes



\### Interview Assistant

\- concise answers

\- STAR format

\- coding help

\- behavioral responses



\### Coding Interview

\- algorithm hints

\- debugging support

\- optimization suggestions



\### System Design

\- architecture suggestions

\- scaling ideas

\- tradeoff analysis



\---



\# 8. Streaming Requirements



Use:

\- WebSockets



Support:

\- Token streaming

\- Incremental UI updates

\- Cancellation

\- Retry/reconnect logic



\---



\# 9. OCR + Screen Analysis Requirements



\## Screen Capture



Electron desktopCapturer support.



\## OCR



Use:

\- Tesseract



\## Features



\- Capture active window

\- OCR coding questions

\- OCR browser text

\- Extract interview prompts



\## Vision AI Optional



Support:

\- GPT-4o vision

\- Gemini vision



\---



\# 10. Frontend UI Requirements



\## UI Design



Modern dark UI.



\## Components



\### Floating Widget

\- microphone indicator

\- connection status

\- compact controls



\### Transcript Panel

\- real-time transcript

\- timestamps

\- speaker labels



\### AI Panel

\- streaming answers

\- markdown rendering

\- syntax highlighting



\### Settings

\- API key management

\- model selection

\- microphone selection

\- theme

\- overlay opacity



\## Styling



Use:

\- TailwindCSS

\- responsive layout

\- animations

\- keyboard-first UX



\---



\# 11. Security Requirements



\## Secrets



Never hardcode API keys.



Use:

\- encrypted local storage

\- environment variables



\## Privacy



Support:

\- local-only mode

\- no transcript persistence

\- configurable logging



\## IPC Security



Electron:

\- contextIsolation enabled

\- disable nodeIntegration in renderer

\- secure preload scripts



\---



\# 12. Local LLM Mode



Support fully local mode using:



\- Ollama

\- LM Studio optional



\## Local Models



Support:

\- llama3

\- qwen

\- deepseek

\- mistral



\## Local Workflow



Audio → Whisper → Local LLM → Overlay



No cloud required.



\---



\# 13. Performance Requirements



\## Startup Time



Target:

\- <3 seconds



\## Memory



Idle target:

\- <500MB



\## Streaming Latency



Target:

\- <2 seconds end-to-end



\---



\# 14. Logging + Monitoring



\## Frontend



Use Winston.



\## Backend



Use Loguru.



\## Log Requirements



\- structured logs

\- rotation

\- error tracking

\- performance timing



\---



\# 15. Testing Requirements



\## Frontend



Use:

\- Vitest

\- Playwright



\## Backend



Use:

\- Pytest



\## Required Coverage



\- WebSocket tests

\- transcription pipeline tests

\- prompt generation tests

\- overlay lifecycle tests



\---



\# 16. Packaging Requirements



\## Electron Builder



Generate:

\- Windows installer

\- macOS app bundle

\- Linux AppImage



\## Auto Updates



Optional support.



\---



\# 17. Folder Structure



project-root/



&#x20;   apps/

&#x20;       desktop/

&#x20;       backend/



&#x20;   packages/

&#x20;       shared/

&#x20;       ui/



&#x20;   scripts/



&#x20;   docs/



\---



\# 18. Backend API Requirements



\## WebSocket Endpoint



/ws/interview



Responsibilities:

\- receive audio chunks

\- stream transcript

\- stream AI answers



\## REST Endpoints



POST /api/settings

GET /api/models

POST /api/ocr

POST /api/session/start

POST /api/session/end



\---



\# 19. Environment Variables



Backend:



OPENAI\_API\_KEY=

GEMINI\_API\_KEY=

OLLAMA\_HOST=

DEFAULT\_MODEL=

WHISPER\_MODEL=



Frontend:



VITE\_BACKEND\_URL=



\---



\# 20. Database Requirements



Use SQLite initially.



Tables:

\- sessions

\- transcripts

\- settings

\- prompts



Optional:

\- PostgreSQL support



\---



\# 21. Production Requirements



The generated code must:



\- use TypeScript strictly

\- use async/await everywhere

\- avoid callback hell

\- include robust error handling

\- include retry logic

\- include reconnection handling

\- include loading states

\- include modular architecture

\- include environment separation

\- include production logging

\- include linting

\- include formatting



\---



\# 22. DevOps Requirements



Include:

\- Docker support

\- docker-compose

\- .env.example

\- Makefile

\- CI/CD GitHub Actions



\---



\# 23. README.md Requirements



Generate a production-grade README.md including:



\- project overview

\- screenshots placeholders

\- architecture diagram

\- installation instructions

\- local development

\- production build

\- Docker setup

\- local LLM setup

\- Whisper setup

\- Electron packaging

\- troubleshooting

\- environment variables

\- keyboard shortcuts

\- security notes



\---



\# 24. Nice-to-Have Features



Optional:

\- memory/context retention

\- voice synthesis

\- AI summaries

\- session export

\- markdown notes

\- interview scoring

\- resume ingestion

\- company-specific preparation

\- leetcode mode



\---



\# 25. Code Quality Rules



Must include:



\- ESLint

\- Prettier

\- Husky hooks

\- type-safe APIs

\- modular services

\- repository pattern

\- clean architecture



\---



\# 26. Explicit Implementation Requirements



The generated project must include:



1\. Working Electron overlay

2\. Working FastAPI backend

3\. Working WebSocket streaming

4\. Working faster-whisper integration

5\. Working OpenAI integration

6\. Working local Ollama integration

7\. Real-time transcript updates

8\. Streaming answer rendering

9\. Production-ready folder structure

10\. README.md

11\. Docker support

12\. Setup scripts



\---



\# 27. Deliverables



Generate:



\- complete source code

\- package.json files

\- requirements.txt

\- Dockerfiles

\- docker-compose.yml

\- tsconfig files

\- Electron config

\- FastAPI app

\- WebSocket implementation

\- README.md

\- .env.example

\- installation scripts



\---



\# 28. Non-Goals



Do NOT:

\- build browser-only app

\- use polling instead of WebSockets

\- use plain JavaScript

\- hardcode secrets

\- use blocking APIs

\- use insecure Electron settings



\---



\# 29. Priority Order



Priority:



1\. Real-time audio pipeline

2\. Overlay UX

3\. Streaming AI responses

4\. Stability

5\. Local-first support

6\. OCR features

7\. Advanced polish



\---



\# 30. Final Goal



The final application should feel like:



\- a native desktop assistant

\- extremely low latency

\- production-grade

\- modular

\- scalable

\- locally runnable

\- extensible for future AI workflows





Generate a production-grade README.md for this project.



The README must include:



\- Overview

\- Features

\- Architecture diagram

\- Tech stack

\- Installation

\- Development setup

\- Backend setup

\- Frontend setup

\- Whisper setup

\- Ollama setup

\- Docker setup

\- Electron packaging

\- Keyboard shortcuts

\- Environment variables

\- Troubleshooting

\- Security considerations

\- Performance tuning

\- FAQ

\- Contribution guide

\- License section



Use professional GitHub README formatting.

Include badges placeholders.

Include screenshots placeholders.

Include Mermaid architecture diagrams.

