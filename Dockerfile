FROM python:3.13-slim

# openssl: makes the certificates on first start (see start.sh)
RUN apt-get update \
    && apt-get install -y --no-install-recommends openssl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir setuptools==76.0.0 requests jsons

COPY NintendoClients/ NintendoClients/
RUN pip install --no-cache-dir NintendoClients/

COPY caddy/ caddy/
COPY coredns/ coredns/
COPY start.sh /start.sh
# a checkout on Windows may have given the script CRLF line endings
RUN sed -i 's/\r$//' /start.sh caddy/Caddyfile coredns/Corefile && chmod +x /start.sh caddy/caddy coredns/coredns

# listen on every interface of the container; start.sh tells the game to use PUBLIC_IP, which you must set
ENV SMM_BIND_IP=0.0.0.0
# where courses come from: CourseWorld (the original Wii U courses, via the Internet Archive) or SMMDB (smmdb.net uploads)
ENV SMM_COURSE_SOURCE=CourseWorld
VOLUME /data

# DNS, HTTP/HTTPS (Caddy), certificate download, course/account files,
# NEX: Super Mario Maker auth + secure, friends auth + secure
EXPOSE 53/udp 53/tcp 80 443 8000 8383 59900/udp 59921/udp 60000/udp 60021/udp

CMD ["bash", "/start.sh"]
