FROM pytorch/pytorch:2.7.1-cuda12.6-cudnn9-runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    INSTANOVO_WORKDIR=/tmp/instanovo_pxd059455

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      curl \
      git \
      libgomp1 \
      procps \
      unzip \
      wget && \
    rm -rf /var/lib/apt/lists/*

RUN python -m pip install --upgrade pip setuptools wheel && \
    python -m pip install \
      instanovo==1.2.2 \
      openpyxl \
      pyarrow \
      pyteomics \
      requests \
      s3fs \
      tqdm

COPY . /app

RUN chmod +x /app/scripts/run_pxd059455_aichor.sh

ENTRYPOINT ["/app/scripts/run_pxd059455_aichor.sh"]
