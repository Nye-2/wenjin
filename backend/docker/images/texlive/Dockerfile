# TeXLive Docker image for LaTeX compilation
# Used by Wenjin (问津) execution service for compiling academic papers

ARG BASE_IMAGE=ubuntu:22.04
FROM ${BASE_IMAGE}

LABEL maintainer="Wenjin Team"
LABEL description="TeXLive 2024 for academic paper compilation"
LABEL version="2024"

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# Optional apt source override for faster regional mirrors
ARG APT_MIRROR=

# Install TeXLive and essential packages
RUN if [ -n "$APT_MIRROR" ]; then \
      sed -i "s|http://archive.ubuntu.com/ubuntu/|$APT_MIRROR|g" /etc/apt/sources.list && \
      sed -i "s|http://security.ubuntu.com/ubuntu/|$APT_MIRROR|g" /etc/apt/sources.list && \
      sed -i "s|http://ports.ubuntu.com/ubuntu-ports/|$APT_MIRROR|g" /etc/apt/sources.list; \
    fi && \
    apt-get update && apt-get install -y --no-install-recommends \
    # Core TeXLive packages
    texlive-latex-base \
    texlive-latex-extra \
    texlive-latex-recommended \
    texlive-fonts-recommended \
    # Science and bibliography
    texlive-science \
    texlive-bibtex-extra \
    biber \
    # XeLaTeX for Chinese/multilingual support
    texlive-xetex \
    texlive-lang-chinese \
    texlive-lang-european \
    # Additional utilities
    ghostscript \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create workspace directory
WORKDIR /workspace

# Default command - can be overridden
ENTRYPOINT ["sh", "-c"]
CMD ["latex --version"]
