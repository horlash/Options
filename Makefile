IMAGE_NAME := horlamy/options-scanner
VERSION := $(shell cat VERSION)

.PHONY: build push build-arm

# Build for the local architecture (usually x86 on Windows)
build:
	docker build -t $(IMAGE_NAME):$(VERSION) -t $(IMAGE_NAME):latest .

# Push both versioned and latest tags to Docker Hub
push:
	docker push $(IMAGE_NAME):$(VERSION)
	docker push $(IMAGE_NAME):latest

# Build explicitly for ARM64 (Raspberry Pi) using buildx
# This requires: docker buildx create --use
build-arm:
	docker buildx build --platform linux/arm64 -t $(IMAGE_NAME):$(VERSION) -t $(IMAGE_NAME):latest --load .

# Push ARM64 build directly to hub (avoids loading into local docker daemon which might fail on x86)
push-arm:
	docker buildx build --platform linux/arm64 -t $(IMAGE_NAME):$(VERSION) -t $(IMAGE_NAME):latest --push .
