FROM node:22-bookworm-slim

WORKDIR /app

RUN corepack enable

COPY frontend/package.json frontend/pnpm-lock.yaml frontend/pnpm-workspace.yaml ./

RUN pnpm install --frozen-lockfile

COPY frontend/ ./

ARG TASKORA_ENV=production
ARG API_URL
ENV TASKORA_ENV=$TASKORA_ENV
ENV API_URL=$API_URL
ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN pnpm run build

ENV NODE_ENV=production

EXPOSE 3000

CMD ["pnpm", "start"]