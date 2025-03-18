#!/bin/bash
PLUGIN_DIR=$PWD/../..
USERNAME=appuser
IMAGE_NAME=debian-vim-ollama

# Ensure the plugin directory exists inside the container
sudo docker run -it --rm --network=host \
  -v "$PLUGIN_DIR:/home/$USERNAME/.vim/pack/test/start/vim-ollama" \
  -u $USERNAME \
  -w /home/$USERNAME \
  $IMAGE_NAME
