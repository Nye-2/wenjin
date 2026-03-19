# AcademiaGPT v2 Frontend

Next.js frontend for AcademiaGPT v2 - an Academic AI Assistant.

## Tech Stack

- Next.js 16 (App Router)
- React 19
- TypeScript
- TailwindCSS
- Zustand
- Axios

## Features
- Workspace management interface
- Paper upload and viewing
- Chat interface with skill selection
- Knowledge panel for artifacts
- Literature panel for references

## Quick Start

```bash
# Install dependencies
npm install

# Copy env template
cp .env.example .env.local

# Start development server
npm run dev

# Build for production
npm run build
```

## Project Structure
```
frontend/
├── app/                    # Next.js App Router pages
│   ├── (auth)/           # Authentication pages
│   ├── (workbench)/      # Workbench layout with panels
│   └── layout.tsx
├── components/              # React components
│   ├── academic/        # Academic components
│   ├── chat/            # Chat components
│   ├── glass/           # Glass morphism UI
│   ├── paper/           # Paper components
│   └── workspace/       # Workspace components
├── lib/                    # Utilities
├── stores/                 # Zustand stores
└── package.json
```

## Pages
- `/` - Landing page
- `/login` - Login page
- `/register` - Registration page
- `/workspaces` - Workspace list
- `/workspaces/[id]` - Workspace detail with:
  - Chat panel
  - Knowledge panel
  - Literature panel

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `NEXT_PUBLIC_API_URL` | Backend API base (e.g. `/api` or `http://localhost:8001/api`) | Recommended |
| `NEXT_PUBLIC_BACKEND_BASE_URL` | Legacy alias for `NEXT_PUBLIC_API_URL` | Optional |
| `NEXT_PUBLIC_LANGGRAPH_BASE_URL` | LangGraph proxy base | Optional |

## License

MIT
