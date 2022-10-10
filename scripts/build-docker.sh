#!/bin/bash

set -xe

git describe --always --tags >glifestream/.version
docker build . -t glifestream
