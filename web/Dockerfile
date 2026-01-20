FROM node:20-alpine

WORKDIR /app

ARG VITE_API_BASE_URL
ARG JUKE_RUNTIME_ENV=development
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV JUKE_RUNTIME_ENV=${JUKE_RUNTIME_ENV}

RUN apk add --no-cache nginx \
	&& mkdir -p /run/nginx \
	&& mkdir -p /usr/share/nginx/html

COPY nginx.conf /etc/nginx/http.d/default.conf

COPY package*.json .npmrc ./
RUN npm install

COPY . .

COPY docker-entrypoint.sh /usr/local/bin/start-web.sh
RUN chmod +x /usr/local/bin/start-web.sh

EXPOSE 5173

ENTRYPOINT ["/usr/local/bin/start-web.sh"]
