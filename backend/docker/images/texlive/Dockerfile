# TeXLive Docker image for LaTeX compilation
# Used by Guanlan (观澜) execution service for compiling academic papers

FROM ubuntu:22.04

LABEL maintainer="Guanlan Team"
LABEL description="TeXLive 2024 for academic paper compilation"
LABEL version="2024"

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# Install TeXLive and essential packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Core TeXLive packages
    texlive-latex-base \
    texlive-latex-extra \
    texlive-latex-recommended \
    texlive-fonts-recommended \
    texlive-fonts-extra \
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
