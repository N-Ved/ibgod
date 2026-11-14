#!/bin/sh
# Put IB God behind the existing Authelia + Caddy + Cloudflare tunnel setup of the n-ved.com `fileserver` stack.
#
# What it changes (each file is backed up first, and every step is validated before anything is reloaded):
#   1. /opt/fileserver/Caddyfile                  + one site block for ibgod.n-ved.com   -> graceful `caddy reload` (no downtime)
#   2. /opt/fileserver/authelia/configuration.yml + 'ibgod.n-ved.com' in the 2FA rule    -> `docker restart authelia` (everyone signs in again once)
# What it never touches: docker-compose.yml of the fileserver stack, FileBrowser, the other sites, secrets.
#
# The third step cannot be scripted from this machine (the tunnel is managed in the Cloudflare dashboard):
#   Zero Trust -> Networks -> Tunnels -> your tunnel -> Public Hostname -> Add:  ibgod.n-ved.com  ->  HTTP  caddy:80
#
# Usage:   sudo sh deploy/go-live.sh            apply
#          sudo sh deploy/go-live.sh rollback   restore the newest backup and reload
set -eu

FS=/opt/fileserver
CADDYFILE=$FS/Caddyfile
AUTHELIA_CFG=$FS/authelia/configuration.yml
BACKUPS=/opt/backups
HOST=ibgod.n-ved.com
AUTHELIA_IMAGE=$(docker inspect authelia --format '{{.Config.Image}}')
MARK="# >>> IB God (managed by /home/student/projects/ibgod/deploy/go-live.sh)"
END="# <<< IB God"

say() { printf '%s\n' "== $*"; }
die() { printf '%s\n' "!! $*" >&2; exit 1; }
probe() { # probe <host> [extra curl args]  -> prints http code and redirect target as seen through Caddy
  h=$1; shift
  docker run --rm --network fileserver_edge curlimages/curl:8.11.1 -s -o /dev/null -m 10 -w '%{http_code} %{redirect_url}' -H "Host: $h" -H 'X-Forwarded-Proto: https' "$@" http://caddy/ 2>/dev/null || echo "000"
}

[ "$(id -u)" = 0 ] || die "run as root (sudo)"
[ -f "$CADDYFILE" ] && [ -f "$AUTHELIA_CFG" ] || die "fileserver stack not found under $FS"

if [ "${1:-}" = "rollback" ]; then
  LAST=$(ls -d $BACKUPS/ibgod-golive-* 2>/dev/null | sort | tail -1)
  [ -n "$LAST" ] || die "no backup found in $BACKUPS"
  say "restoring from $LAST"
  cat "$LAST/Caddyfile" > "$CADDYFILE"                      # same inode: the file is a single-file bind mount
  cat "$LAST/configuration.yml" > "$AUTHELIA_CFG"
  docker exec caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1 || die "restored Caddyfile does not validate"
  docker exec caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1
  docker restart authelia >/dev/null
  say "rolled back. docs: $(probe docs.n-ved.com)"
  exit 0
fi

docker inspect ibgod --format '{{.State.Health.Status}}' 2>/dev/null | grep -q healthy || die "the ibgod container is not running/healthy: run 'docker compose up -d' in /home/student/projects/ibgod first"
docker network inspect fileserver_apps --format '{{range .Containers}}{{.Name}} {{end}}' | grep -qw ibgod || die "ibgod is not attached to the fileserver_apps network"

TS=$(date +%Y%m%d-%H%M%S)
BK=$BACKUPS/ibgod-golive-$TS
mkdir -p "$BK" && chmod 700 "$BK"
cp -p "$CADDYFILE" "$BK/Caddyfile"
cp -p "$AUTHELIA_CFG" "$BK/configuration.yml"
say "backups in $BK"
BEFORE_DOCS=$(probe docs.n-ved.com); BEFORE_VIEW=$(probe view.n-ved.com)
say "before: docs -> $BEFORE_DOCS | view -> $BEFORE_VIEW"

# ---- 1. Caddy ---------------------------------------------------------------------------------------------------
if grep -q "http://$HOST" "$CADDYFILE"; then
  say "Caddyfile already has a block for $HOST (left as is)"
else
  TMP=$(mktemp "$BK/tmp.XXXXXX")
  awk -v mark="$MARK" -v end="$END" -v host="$HOST" '
    /^# Anything else that reaches the tunnel: drop it\./ && !done {
      print mark
      print "# Study planner. Runs as its own compose project; the container `ibgod` sits on the apps network."
      print "# The app trusts Remote-User ONLY from Caddy, so Authelia must stay in front of every request."
      print "http://" host " {"
      print "\timport secure_headers"
      print "\timport same_origin_only"
      print "\trequest_body {"
      print "\t\tmax_size 25MB"
      print "\t}"
      print "\timport authelia"
      print "\treverse_proxy ibgod:8080"
      print "}"
      print end
      print ""
      done = 1
    }
    { print }
    END { if (!done) exit 3 }' "$CADDYFILE" > "$TMP" || { rm -f "$TMP"; die "could not find the catch-all block in the Caddyfile; nothing changed"; }
  cat "$TMP" > "$CADDYFILE"; rm -f "$TMP"                   # write in place: keeps the inode the container has mounted
  if ! docker exec caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>"$BK/caddy-validate.log"; then
    cat "$BK/Caddyfile" > "$CADDYFILE"
    die "new Caddyfile failed validation (see $BK/caddy-validate.log); original restored, nothing reloaded"
  fi
  docker exec caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1 || { cat "$BK/Caddyfile" > "$CADDYFILE"; die "caddy reload failed; original restored"; }
  say "Caddy reloaded with the $HOST block"
fi

# ---- 2. Authelia ------------------------------------------------------------------------------------------------
if grep -q "'$HOST'" "$AUTHELIA_CFG"; then
  say "Authelia already knows $HOST (left as is)"
else
  TMP=$(mktemp "$BK/tmp.XXXXXX")
  awk -v host="$HOST" '
    { print }
    /^[[:space:]]*-[[:space:]]*.view\.n-ved\.com.[[:space:]]*$/ && !done { line = $0; sub(/view\.n-ved\.com/, host, line); print line; done = 1 }
    END { if (!done) exit 3 }' "$AUTHELIA_CFG" > "$TMP" || { rm -f "$TMP"; die "could not find the view.n-ved.com rule in the Authelia config; Authelia left unchanged (Caddy change is harmless: the new site just answers 403 until Authelia allows it)"; }
  # Validate the new file with the same image and secrets before touching the running service.
  if ! docker run --rm --network none --user 8000:8000 \
        -e AUTHELIA_IDENTITY_VALIDATION_RESET_PASSWORD_JWT_SECRET_FILE=/secrets/authelia_jwt_secret -e AUTHELIA_SESSION_SECRET_FILE=/secrets/authelia_session_secret \
        -e AUTHELIA_STORAGE_ENCRYPTION_KEY_FILE=/secrets/authelia_storage_key -e AUTHELIA_AUTHENTICATION_BACKEND_LDAP_PASSWORD_FILE=/secrets/authelia_ldap_password \
        -e AUTHELIA_NOTIFIER_SMTP_PASSWORD_FILE=/secrets/smtp_password \
        -v "$TMP:/config/configuration.yml:ro" -v "$FS/secrets/authelia:/secrets:ro" "$AUTHELIA_IMAGE" authelia config validate --config /config/configuration.yml >"$BK/authelia-validate.log" 2>&1; then
    rm -f "$TMP"
    die "new Authelia config failed validation (see $BK/authelia-validate.log); Authelia left unchanged"
  fi
  cat "$TMP" > "$AUTHELIA_CFG"; rm -f "$TMP"                # in place: keeps owner 8000 and mode
  say "restarting Authelia (everyone signs in again once)"
  docker restart authelia >/dev/null
  ok=0
  for i in $(seq 1 30); do
    [ "$(docker inspect authelia --format '{{.State.Health.Status}}' 2>/dev/null)" = healthy ] && { ok=1; break; }
    sleep 2
  done
  if [ $ok != 1 ]; then
    say "Authelia did not become healthy: restoring the previous config"
    cat "$BK/configuration.yml" > "$AUTHELIA_CFG"
    docker restart authelia >/dev/null
    die "Authelia rolled back to the previous config. Check 'docker logs authelia'."
  fi
  say "Authelia is healthy with the new rule"
fi

# ---- 3. Verify --------------------------------------------------------------------------------------------------
AFTER_DOCS=$(probe docs.n-ved.com); AFTER_VIEW=$(probe view.n-ved.com)
NEW=$(probe $HOST); SPOOF=$(probe $HOST -H 'Remote-User: admin')
say "after:  docs -> $AFTER_DOCS | view -> $AFTER_VIEW"
say "$HOST without login        -> $NEW"
say "$HOST with a forged Remote-User header -> $SPOOF"
[ "$AFTER_DOCS" = "$BEFORE_DOCS" ] && [ "$AFTER_VIEW" = "$BEFORE_VIEW" ] || die "existing sites answer differently than before. Run: sudo sh $0 rollback"
case "$NEW" in 302*auth.n-ved.com*) ;; *) die "$HOST is not being sent to the Authelia login as expected";; esac
case "$SPOOF" in 302*auth.n-ved.com*) ;; *) die "a forged identity header was not stopped by Authelia. Run: sudo sh $0 rollback";; esac
say "done. Last step (Cloudflare dashboard): add public hostname $HOST -> HTTP caddy:80 on the tunnel."
