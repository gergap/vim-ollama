FROM debian:12

# Create a user with UID 1000
RUN useradd -m -u 1000 -s /bin/bash appuser

# Note: vim packages does not include Python3 support,
# so we need to install python-nox (no X)

# Install necessary packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends vim-nox git python3-pip python3-venv && \
    rm -rf /var/lib/apt/lists/*

# Switch to the new user
USER appuser

# Create .vim dir with user permissions
RUN mkdir ~/.vim
COPY .vimrc /home/appuser/.vimrc

# Set the working directory
WORKDIR /home/appuser
