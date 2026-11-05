# Стадии (D-048):
#   test    — зависимости и исходники; запускает Vitest (compose-сервис frontend-tests);
#   build   — сборка статики Vite;
#   runtime — nginx раздаёт статику и проксирует /api на backend (compose-сервис frontend).
FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund


FROM deps AS test
COPY . .
CMD ["npx", "vitest", "run"]


FROM deps AS build
COPY . .
RUN npm run build


FROM nginx:1.28-alpine AS runtime
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY security-headers.conf /etc/nginx/snippets/security-headers.conf
COPY --from=build /app/dist /usr/share/nginx/html
