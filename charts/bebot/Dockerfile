#dockerfile:alpine_python_bebot
FROM python:3.14-alpine
ENV PYTHONUNBUFFERED=1
RUN apk --no-cache add tini && \
    addgroup -S bebot && adduser -S -G bebot -u 1000 bebot
COPY app /BeBot
RUN pip install --no-cache-dir -r /BeBot/requirements.txt && \
    chown -R bebot:bebot /BeBot
COPY docker-entrypoint.sh /BeBot/docker-entrypoint.sh
RUN chmod +x /BeBot/docker-entrypoint.sh
WORKDIR /BeBot
USER bebot
ENTRYPOINT ["/sbin/tini", "-g", "--"]
CMD ["/BeBot/docker-entrypoint.sh"]
