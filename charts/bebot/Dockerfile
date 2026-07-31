#dockerfile:alpine_php_bebot
FROM alpine:3.24.1
RUN apk --no-cache add \
    php85-cli php85-phar php85-curl php85-sockets php85-pdo php85-pdo_mysql \
    php85-mbstring php85-ctype php85-bcmath php85-json php85-posix php85-xml php85-simplexml \
    php85-dom php85-pcntl php85-zip php85-fileinfo php85-mysqli php85-pecl-redis tini && \
    ln -sf /usr/bin/php85 /usr/bin/php && \
    addgroup -S bebot && adduser -S -G bebot -u 1000 bebot
COPY vendor/BeBot /BeBot
COPY docker-entrypoint.sh /BeBot/docker-entrypoint.sh
RUN chmod +x /BeBot/docker-entrypoint.sh && chown -R bebot:bebot /BeBot
WORKDIR /BeBot
USER bebot
ENTRYPOINT ["/sbin/tini", "-g", "--"]
CMD ["/BeBot/docker-entrypoint.sh"]
