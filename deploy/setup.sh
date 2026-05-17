#!/bin/bash
# One-time EC2 setup script for cody.danblanco.dev
# Run as ubuntu user on a fresh Ubuntu 22.04 ARM (t4g.small) instance
set -e

# --- Docker ---
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER

# --- Nginx + Certbot ---
sudo apt-get install -y nginx certbot python3-certbot-nginx

# --- Clone repo ---
git clone https://github.com/Danultimate/cody.git ~/cody
cd ~/cody

# --- Create .env (edit after cloning) ---
cat > .env <<'ENV'
GEMINI_API_KEY=REPLACE_ME
VOYAGE_API_KEY=REPLACE_ME

POSTGRES_USER=cody
POSTGRES_PASSWORD=REPLACE_WITH_STRONG_PASSWORD
POSTGRES_DB=cody

CORS_ORIGINS=https://cody.danblanco.dev
ENV

echo ""
echo "=== Edit ~/cody/.env with your API keys, then run: ==="
echo "  cd ~/cody"
echo "  docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build"
echo ""
echo "=== Then set up nginx + SSL: ==="
echo "  sudo cp ~/cody/deploy/nginx.conf /etc/nginx/sites-available/cody.danblanco.dev"
echo "  sudo ln -s /etc/nginx/sites-available/cody.danblanco.dev /etc/nginx/sites-enabled/"
echo "  sudo nginx -t && sudo systemctl reload nginx"
echo "  sudo certbot --nginx -d cody.danblanco.dev"
echo ""
echo "=== Finally, index the Cody repo itself as the demo dataset: ==="
echo "  docker compose --profile ingest run --rm ingestion python main.py --github https://github.com/Danultimate/cody"
