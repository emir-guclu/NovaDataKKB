# ---- deps: bağımlılıkları kur ----
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ---- builder: uygulamayı derle ----
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules

# Kaynak dosyalar tek tek listeleniyor (node_modules, .next, .env.local gibi
# yerel/host'a özgü dizinleri build context'ten dışlayan bir frontend/.dockerignore
# olmadığından, host'taki node_modules'ün burayı ezmesini engellemek için).
COPY package.json package-lock.json next.config.ts tsconfig.json \
     postcss.config.mjs eslint.config.mjs middleware.ts ./
COPY app ./app
COPY i18n ./i18n
COPY lib ./lib
COPY messages ./messages
COPY public ./public

# NEXT_PUBLIC_* değişkenleri Next.js tarafından yalnızca build anında
# client bundle'a gömülür; bu yüzden runtime env değil, build argümanı olmalı.
ARG NEXT_PUBLIC_API_BASE_URL
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL

RUN npm run build

# ---- runner: üretim çalıştırma ----
FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json
COPY --from=builder /app/next.config.ts ./next.config.ts
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/public ./public
COPY --from=builder /app/i18n ./i18n
COPY --from=builder /app/messages ./messages
COPY --from=builder /app/middleware.ts ./middleware.ts

EXPOSE 3000

CMD ["npm", "start"]
