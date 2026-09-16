# apps/web/Dockerfile — Next.js production imajı.
#
# ÖNEMLİ: build context REPO KÖKÜ olmalı (kök `docker-compose.yml`'de
# `context: .`), çünkü `package-lock.json` + kaynak kod `apps/web/`
# altında. `next.config.ts::output: "standalone"` (bu görev kapsamında
# eklendi) sayesinde son imaj `node_modules`'ın TAMAMINI DEĞİL, yalnızca
# gerçekten kullanılan bağımlılıkları içeren küçük bir sunucu paketi
# taşır.

FROM node:22-slim AS deps
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

FROM node:22-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY apps/web ./
# BACKEND_INTERNAL_URL build anında gerekmiyor — yalnızca `next.config.
# ts::rewrites()` runtime'da (container başlarken) okunur; `NEXT_PUBLIC_*`
# olmayan bir env değişkeni build'e "gömülmez".
RUN npm run build

FROM node:22-slim AS runner
WORKDIR /app
ENV NODE_ENV=production PORT=3000 HOSTNAME=0.0.0.0

# `standalone` çıktısı kendi minimal `node_modules`'ını + `server.js`'i
# içerir; `public/` ve `.next/static/` ayrıca kopyalanmalı (Next.js'in
# resmi standalone dağıtım deseni).
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD node -e "fetch('http://localhost:3000/').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "server.js"]
