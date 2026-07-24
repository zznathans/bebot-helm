#dockerfile:alpine_php_bebot
FROM alpine:3.24.1
RUN apk --no-cache add \
    git php85-cli php85-phar php85-curl php85-sockets php85-pdo php85-pdo_mysql \
    php85-mbstring php85-ctype php85-bcmath php85-json php85-posix php85-xml php85-simplexml \
    php85-dom php85-pcntl php85-zip php85-opcache php85-fileinfo php85-mysqli tini && \
    ln -sf /usr/bin/php85 /usr/bin/php && \
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
