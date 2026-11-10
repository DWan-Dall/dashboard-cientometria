FROM php:8.3-cli

# R é opcional: a triagem é feita só pelo pacote Python. R serve apenas para o
# relatório bibliometrix complementar (R/relatorio_bibliometrix.Rmd). Ative com
#   docker build --build-arg COM_R=1 -t dashboard-cientometria .
ARG COM_R=0

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip python3-venv \
    && if [ "$COM_R" = "1" ]; then \
         apt-get install -y --no-install-recommends r-base r-base-dev libcurl4-openssl-dev libssl-dev libxml2-dev \
         && Rscript -e "install.packages(c('bibliometrix','rmarkdown'), repos='https://cloud.r-project.org')"; \
       fi \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    MPLBACKEND=Agg \
    CIENTOMETRIA_PROJETOS=/dados/projetos

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY . /app
RUN mkdir -p /dados/projetos /app/tmp_uploads/plots

# Dados de projetos (exportações licenciadas) ficam fora da imagem, num volume.
VOLUME ["/dados"]
EXPOSE 8000

CMD ["php", "-d", "upload_max_filesize=256M", "-d", "post_max_size=256M", "-d", "max_file_uploads=100", "-d", "max_execution_time=0", "-S", "0.0.0.0:8000", "-t", "/app"]
