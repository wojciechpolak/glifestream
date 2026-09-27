"""
# The image's DJANGO_SETTINGS_MODULE. The Docker settings live in
# glifestream/settings_docker.py; a run/ mounted from an empty directory gets
# this file on the first start, and a run/settings_docker.py of your own wins.
"""

from glifestream.settings_docker import *  # noqa: F403
