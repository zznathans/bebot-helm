#dockerfile:alpine_php_bebot
FROM alpine:3.24.1
RUN apk --no-cache add \
    git php83-cli php83-phar php83-curl php83-sockets php83-pdo php83-pdo_mysql \
    php83-mbstring php83-ctype php83-bcmath php83-json php83-posix php83-xml php83-simplexml \
    php83-dom php83-pcntl php83-zip php83-opcache php83-fileinfo php83-mysqli tini && \
    ln -sf /usr/bin/php83 /usr/bin/php && \
    git clone https://github.com/J-Soft/BeBot.git /BeBot && \
    git -C /BeBot checkout f4cf0c7a6662e530c94c8428e3728be899827176 && \
    addgroup -S bebot && adduser -S -G bebot -u 1000 bebot && \
    chown -R bebot:bebot /BeBot
COPY docker-entrypoint.sh /BeBot/docker-entrypoint.sh
RUN chmod +x /BeBot/docker-entrypoint.sh
WORKDIR /BeBot
USER bebot
ENTRYPOINT ["/sbin/tini", "-g", "--"]
CMD ["/BeBot/docker-entrypoint.sh"]
