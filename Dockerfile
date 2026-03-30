FROM php:8.3-cli

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv \
        r-base r-base-dev \
        libcurl4-openssl-dev libssl-dev libxml2-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

RUN Rscript -e "install.packages(c('jsonlite','readxl','ggplot2'), repos='https://cloud.r-project.org')"

COPY . /app

EXPOSE 8000

CMD ["php", "-S", "0.0.0.0:8000", "-t", "/app"]
