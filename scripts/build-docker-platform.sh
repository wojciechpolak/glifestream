#!/bin/bash

set -xe

PLATFORM=${PLATFORM:-linux/amd64}

git describe --always --tags >glifestream/.version
docker build . -t wap/glifestream --platform $PLATFORM
