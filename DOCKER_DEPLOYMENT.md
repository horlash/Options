# Docker Deployment Guide - NewScanner v1.0.1

## Multi-Platform Build

This image is built for:
- **linux/amd64** - Windows, Linux x86_64
- **linux/arm64** - Raspberry Pi 4/5

---

## Deploying to Docker Hub

### 1. Build and Push (Windows PC)

```bash
# Run the deployment script
.\deploy_docker.bat
```

This will:
1. Check Docker is running
2. Verify Docker Hub login
3. Build for both platforms
4. Push to `horlash/newscanner:1.0.1` and `latest`

**Manual command:**
```bash
docker buildx build --platform linux/amd64,linux/arm64 \
  -t horlash/newscanner:1.0.1 \
  -t horlash/newscanner:latest \
  --push .
```

---

## Running on Raspberry Pi

### 1. Pull the Image
```bash
docker pull horlash/newscanner:1.0.1
```

### 2. Run the Container
```bash
docker run -d \
  --name newscanner \
  -p 5000:5000 \
  --restart unless-stopped \
  horlash/newscanner:1.0.1
```

### 3. Check Logs
```bash
docker logs -f newscanner
```

### 4. Access the App
- Local: http://localhost:5000
- Login: admin / Rkelly080

---

## Sharing via Ngrok (Raspberry Pi)

### Option 1: Ngrok in Separate Container
```bash
# Install ngrok
curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/trusted.gpg.d/ngrok.asc >/dev/null
echo "deb https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list
sudo apt update && sudo apt install ngrok

# Run ngrok
ngrok http 5000
```

### Option 2: Run Ngrok in Docker
```bash
docker run -d \
  --name ngrok \
  --net=host \
  ngrok/ngrok:latest http 5000 --authtoken YOUR_NGROK_TOKEN
```

---

## Updating the Image

### On Windows PC:
```bash
# Make code changes
git commit -am "Update description"

# Rebuild and push
.\deploy_docker.bat
```

### On Raspberry Pi:
```bash
# Pull latest
docker pull horlash/newscanner:latest

# Stop old container
docker stop newscanner
docker rm newscanner

# Run new version
docker run -d --name newscanner -p 5000:5000 --restart unless-stopped horlash/newscanner:latest
```

---

## Troubleshooting

### Image won't run on Raspberry Pi
```bash
# Check platform
docker inspect horlash/newscanner:1.0.1 | grep Architecture

# Should show: "Architecture": "arm64"
```

### Build fails on Windows
```bash
# Ensure buildx is set up
docker buildx ls

# Should see mybuilder with arm64 support
```

### Can't push to Docker Hub
```bash
# Re-login
docker login

# Verify credentials
docker info | grep Username
```

---

## Version History

- **1.0.1** (2026-02-11) - Multi-platform support, LEAP filter fixes
- **1.0.0** - Initial release
