# Imagem base oficial do PHP; pode apontar para um espelho (ex.: mirror.gcr.io/library/php:8.3-cli-bookworm)
# quando o Docker Hub limitar requisições:  --build-arg IMAGEM_BASE=...
ARG IMAGEM_BASE=php:8.3-cli-bookworm
FROM ${IMAGEM_BASE}

# R é opcional: a triagem é feita só pelo pacote Python. R serve apenas para o
# relatório bibliometrix complementar (R/relatorio_bibliometrix.Rmd). Ative com
#   docker build --build-arg COM_R=1 -t dashboard-cientometria .
ARG COM_R=0

# Proxy opcional no build (redes corporativas / ambientes com inspeção TLS):
#   docker build --network host --build-arg HTTPS_PROXY=http://proxy:porta \
#     --secret id=ca_proxy,src=/caminho/ca.crt -t dashboard-cientometria .
# A CA só é usada durante este RUN e é removida no fim (não fica na imagem).
RUN --mount=type=secret,id=ca_proxy,required=false \
    set -eu; \
    if [ -f /run/secrets/ca_proxy ]; then \
      cp /run/secrets/ca_proxy /usr/local/share/ca-certificates/ca_proxy_build.crt && update-ca-certificates >/dev/null; \
    fi; \
    if [ -n "${HTTPS_PROXY:-}" ]; then \
      sed -i 's#http://deb.debian.org#https://deb.debian.org#g' /etc/apt/sources.list.d/debian.sources; \
      printf 'Acquire::https::Proxy "%s";\n' "$HTTPS_PROXY" > /etc/apt/apt.conf.d/90proxy_build; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends python3 python3-pip python3-venv curl; \
    if [ "$COM_R" = "1" ]; then \
      apt-get install -y --no-install-recommends r-base r-base-dev libcurl4-openssl-dev libssl-dev libxml2-dev; \
      Rscript -e "install.packages(c('bibliometrix','rmarkdown'), repos='https://cloud.r-project.org')"; \
    fi; \
    python3 -m venv /opt/venv; \
    rm -rf /var/lib/apt/lists/* /etc/apt/apt.conf.d/90proxy_build; \
    sed -i 's#https://deb.debian.org#http://deb.debian.org#g' /etc/apt/sources.list.d/debian.sources; \
    if [ -f /usr/local/share/ca-certificates/ca_proxy_build.crt ]; then \
      rm -f /usr/local/share/ca-certificates/ca_proxy_build.crt && update-ca-certificates --fresh >/dev/null; \
    fi

WORKDIR /app

ENV PATH="/opt/venv/bin:$PATH" \
    MPLBACKEND=Agg \
    PYTHONDONTWRITEBYTECODE=1 \
    CIENTOMETRIA_PROJETOS=/dados/projetos \
    CIENTOMETRIA_DIR_UPLOAD=/tmp/cientometria_upload

COPY requirements.txt /tmp/requirements.txt
RUN --mount=type=secret,id=ca_proxy,required=false \
    if [ -f /run/secrets/ca_proxy ]; then export PIP_CERT=/run/secrets/ca_proxy; fi; \
    pip install --no-cache-dir -r /tmp/requirements.txt

COPY . /app

# Usuário sem privilégios; o código fica somente leitura para ele.
RUN useradd --system --uid 10001 --home-dir /nonexistent --shell /usr/sbin/nologin app \
    && mkdir -p /dados/projetos \
    && chown -R app:app /dados \
    && chmod -R a-w /app
USER app

# Dados de projetos (exportações licenciadas) ficam fora da imagem, num volume.
VOLUME ["/dados"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS -o /dev/null http://127.0.0.1:8000/ || exit 1

# router.php: só os pontos de entrada PHP são servidos (nunca /dados, código ou .git).
CMD ["php", "-d", "upload_max_filesize=512M", "-d", "post_max_size=512M", "-d", "max_file_uploads=50", \
     "-d", "max_execution_time=0", "-d", "expose_php=0", "-S", "0.0.0.0:8000", "router.php"]
