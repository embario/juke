FROM node:20-alpine

WORKDIR /app

ARG VITE_API_BASE_URL
ARG DISABLE_REGISTRATION
ARG JUKE_RUNTIME_ENV=development
ARG BACKEND_URL
ARG WEB_PORT
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV DISABLE_REGISTRATION=${DISABLE_REGISTRATION}
ENV JUKE_RUNTIME_ENV=${JUKE_RUNTIME_ENV}
ENV BACKEND_URL=${BACKEND_URL}
ENV WEB_PORT=${WEB_PORT}

RUN apk add --no-cache nginx gettext \
	&& mkdir -p /run/nginx \
	&& mkdir -p /usr/share/nginx/html

COPY nginx.conf /etc/nginx/http.d/default.conf.template

COPY package*.json .npmrc ./
RUN npm install

COPY . .

COPY docker-entrypoint.sh /usr/local/bin/start-web.sh
RUN chmod +x /usr/local/bin/start-web.sh

EXPOSE ${WEB_PORT}

ENTRYPOINT ["/usr/local/bin/start-web.sh"]
