#!/bin/bash
# Starts everything in the container.
#   PUBLIC_IP  required: the LAN address of the computer that runs the container (what the Wii U / Cemu connects to)
#   DATA_DIR   where the certificates are kept between runs (default /data; mount a volume there)
set -eu

if [ -z "${PUBLIC_IP:-}" ]; then
    echo "PUBLIC_IP is not set. Start the container with -e PUBLIC_IP=<the LAN address of this computer>, e.g. 192.168.1.20" >&2
    exit 1
fi
case "$PUBLIC_IP" in
    *[!0-9.]* | "" ) echo "PUBLIC_IP must be an IPv4 address such as 192.168.1.20 (got '$PUBLIC_IP')" >&2; exit 1 ;;
esac

DATA="${DATA_DIR:-/data}"
CERTS="$DATA/certs"
WIIU="$DATA/wii-u-certificates"
RUN=/tmp/run
mkdir -p "$CERTS" "$WIIU" "$RUN"

# --- certificates -------------------------------------------------------------------------------------------------------
# One CA per installation, made on first start and kept in the data volume. Its private key (ca.key) never leaves
# $CERTS; only the public certificate is offered for download (port 8000), as the files the Wii U / Cemu must trust.
if [ ! -s "$CERTS/ca.pem" ] || [ ! -s "$CERTS/ca.key" ]; then
    echo "[start] creating a new certificate authority"
    openssl req -x509 -newkey rsa:2048 -nodes -sha256 -days 3650 \
        -keyout "$CERTS/ca.key" -out "$CERTS/ca.pem" -subj "/CN=SMM home server CA"
    rm -f "$CERTS"/*.crt   # certificates signed by a previous CA are no longer valid
fi
chmod 600 "$CERTS/ca.key"

for host in account.nintendo.net wup-ama.app.nintendo.net; do
    if [ ! -s "$CERTS/$host.crt" ]; then
        echo "[start] creating the certificate for $host"
        openssl req -newkey rsa:2048 -nodes -keyout "$CERTS/$host.pem" -out "$CERTS/$host.csr" -subj "/CN=$host"
        printf 'subjectAltName=DNS:%s\nextendedKeyUsage=serverAuth\nbasicConstraints=CA:FALSE\n' "$host" > "$CERTS/$host.ext"
        openssl x509 -req -sha256 -days 3650 -in "$CERTS/$host.csr" -extfile "$CERTS/$host.ext" \
            -CA "$CERTS/ca.pem" -CAkey "$CERTS/ca.key" -CAcreateserial -out "$CERTS/$host.leaf"
        cat "$CERTS/$host.leaf" "$CERTS/ca.pem" > "$CERTS/$host.crt"
    fi
done

# the public certificate, named as before (only this is offered for download, never the private key)
rm -f "$WIIU"/*
openssl x509 -in "$CERTS/ca.pem" -outform DER -out "$WIIU/ca.der"
echo "Copy all the following files into the Wii U system store mlc01/sys/title/0005001b10054000/content/scerts/" > "$WIIU/README.txt"
for name in CACERT_NINTENDO_CA CACERT_NINTENDO_CA_G2 CACERT_NINTENDO_CA_G3 \
            CACERT_NINTENDO_CLASS2_CA CACERT_NINTENDO_CLASS2_CA_G2 CACERT_NINTENDO_CLASS2_CA_G3; do
    cp "$WIIU/ca.der" "$WIIU/$name.der.proxy"
done
rm "$WIIU/ca.der"

# --- configuration ------------------------------------------------------------------------------------------------------
sed "s#@PUBLIC_IP@#$PUBLIC_IP#g" /app/coredns/Corefile > "$RUN/Corefile"
sed "s#@CERTS@#$CERTS#g" /app/caddy/Caddyfile > "$RUN/Caddyfile"

export SMM_BIND_IP="${SMM_BIND_IP:-0.0.0.0}"
export SMM_PUBLIC_IP="$PUBLIC_IP"

# --- servers ------------------------------------------------------------------------------------------------------------
cd /app/NintendoClients
python account_server.py &
python example_smm_server.py &
python example_friend_server.py &
python -m http.server 8000 --directory "$WIIU" &
# the course downloader: fills www/ with courses for the lists (without it every list is empty). It is restarted if it
# stops, e.g. while the computer has no internet, so it never takes the other servers down with it.
( while true; do python smmdb.py || true; sleep 30; done ) &
cd /app
./caddy/caddy -conf "$RUN/Caddyfile" -agree &
./coredns/coredns -conf "$RUN/Corefile" -dns.port=53 &

echo "[start] up. The game is told to use $PUBLIC_IP. Certificates to install: http://$PUBLIC_IP:8000/"

# stop everything if any one of them dies, so the problem is visible instead of half a server running
wait -n
status=$?
echo "[start] a server stopped (exit $status); shutting down" >&2
kill $(jobs -p) 2>/dev/null || true
exit 1
