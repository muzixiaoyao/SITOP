FROM docker.m.daocloud.io/node:20-alpine AS builder

WORKDIR /app

COPY package.json ./
RUN npm install --registry=https://registry.npmmirror.com

COPY . .
RUN npx vite build

# Production stage - serve with nginx
FROM docker.m.daocloud.io/nginx:alpine

# Fix pid file location for compatibility (旧内核 /run 不可写)
RUN sed -i 's|/run/nginx.pid|/tmp/nginx.pid|g' /etc/nginx/nginx.conf

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

# Run nginx in foreground without pid file
CMD ["nginx", "-g", "daemon off;"]
