# Hostinger VPS Deployment Guide — Student Assistant

Self-hosted stack: **Nginx (HTTPS) → FastAPI backend → MongoDB**, via Docker Compose. No Emergent runtime.

## 0. Prerequisites
- Hostinger VPS (Ubuntu 22.04+), 2 vCPU / 4 GB RAM recommended.
- Domain `ravindertulsiani.com` with an `A` record `api.ravindertulsiani.com` → VPS IP.
- Your **OpenAI API key** and **Google OAuth Web Client ID**.

## 1. Install Docker
```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker
```

## 2. Get the code & configure
```bash
git clone <your-repo> student-assistant && cd student-assistant
cp .env.example backend/.env
nano backend/.env          # set OPENAI_API_KEY, GOOGLE_CLIENT_ID, JWT_SECRET (openssl rand -hex 32),
                           # CORS_ORIGINS, ALLOW_INSECURE_DEV=false
```

## 3. TLS certificate (Let's Encrypt)
```bash
sudo apt install -y certbot
sudo mkdir -p /var/www/certbot
# Temporarily serve port 80 or use standalone:
sudo certbot certonly --standalone -d api.ravindertulsiani.com
# Certs land in /etc/letsencrypt/live/api.ravindertulsiani.com/
```

## 4. Launch
```bash
bash deploy/deploy.sh
```
This builds the backend image, starts Mongo + backend + Nginx, and checks `/api/health`.

## 5. Firewall
```bash
sudo ufw allow OpenSSH && sudo ufw allow 80 && sudo ufw allow 443 && sudo ufw enable
```
Do **not** expose Mongo (27017) publicly — it stays on the internal Docker network.

## 6. Point the app at the backend
In `frontend/.env` (or EAS build env):
```
EXPO_PUBLIC_BACKEND_URL=https://api.ravindertulsiani.com
EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID=<web client id>
EXPO_PUBLIC_GOOGLE_ANDROID_CLIENT_ID=<android client id>
```

## 7. Operate
- Logs: `docker compose -f docker-compose.production.yml logs -f backend`
- Backup: `bash deploy/backup.sh` (cron nightly: `0 3 * * * cd /path && bash deploy/backup.sh`)
- Restore: `bash deploy/restore.sh backups/<file>`
- Update: `bash deploy/update.sh`
- Cert renewal: `certbot renew` (add cron; then `docker compose restart nginx`)

## 8. Log rotation
Docker `json-file` logs — add `/etc/docker/daemon.json`:
```json
{ "log-driver": "json-file", "log-opts": { "max-size": "10m", "max-file": "5" } }
```
then `sudo systemctl restart docker`.

## New-operator smoke test (deployment test)
1. Set env → `bash deploy/deploy.sh` → `curl https://api.ravindertulsiani.com/api/health` returns `status: ok`.
2. Install the APK, sign in with Google, capture a sentence, confirm a task appears, run a search.
3. `bash deploy/backup.sh` then `restore.sh` on a scratch DB.
