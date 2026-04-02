FROM node:22-bookworm-slim

WORKDIR /workspace/apps/web

COPY apps/web/package.json ./

RUN corepack enable

COPY apps/web ./

EXPOSE 5173

CMD ["bash", "-lc", "pnpm install && pnpm dev --host 0.0.0.0 --port 5173"]
