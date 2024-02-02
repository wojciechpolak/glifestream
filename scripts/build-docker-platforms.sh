#!/bin/bash

set -e

PLATFORMS=${PLATFORMS:-linux/amd64,linux/arm64}

git describe --always --tags >glifestream/.version

# Split the platforms into an array
IFS=',' read -ra PLATFORM_ARRAY <<< "$PLATFORMS"

for PLATFORM in "${PLATFORM_ARRAY[@]}"; do
    # Check if the platform contains a slash
    if [[ $PLATFORM == *"/"* ]]; then
        ARCH=$(echo $PLATFORM | cut -d'/' -f2)
        OS=$(echo $PLATFORM | cut -d'/' -f1)
    else
        ARCH=$PLATFORM
        OS="linux"
        PLATFORM="${OS}/${ARCH}"
    fi

    # Construct image name without the OS prefix
    IMAGE_NAME="wap/glifestream/${ARCH}"

    set -xe
    docker build . -t $IMAGE_NAME --platform $PLATFORM
done
