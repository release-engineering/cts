FROM fedora:36 AS builder
WORKDIR /src
RUN dnf -y install git
COPY . .
RUN sed -i -e "s/version=.*/version='$(./get-version.sh)',/" setup.py


FROM fedora:36

ARG cacert_url=undefined
ARG build_date=unknown

LABEL \
    name="CTS" \
    maintainer="CTS developers" \
    license="MIT" \
    build-date=$build_date

WORKDIR /src

RUN dnf -y update && dnf -v -y install \
        httpd \
        mod_auth_gssapi \
        mod_ldap \
        mod_ssl \
        python3-defusedxml \
        python3-fedora \
        python3-flask \
        python3-flask-login \
        python3-flask-migrate \
        python3-flask-sqlalchemy \
        python3-ldap \
        python3-mod_wsgi \
        python3-openidc-client \
        python3-pip \
        python3-productmd \
        python3-prometheus_client \
        python3-psutil \
        python3-psycopg2 \
        python3-pyOpenSSL \
        python3-sqlalchemy \
        python3-systemd \
        systemd \
    && dnf -v -y install net-tools iproute iputils traceroute \
    && dnf -y clean all \
    && rm -f /tmp/*

RUN if [ "$cacert_url" != "undefined" ]; then \
        cd /etc/pki/ca-trust/source/anchors \
        && curl -O --insecure $cacert_url \
        && update-ca-trust extract; \
    fi

RUN chmod 755 /var/log/httpd

COPY --from=builder /src .

RUN mkdir -p /usr/share/cts && cp contrib/cts.wsgi /usr/share/cts/

RUN pip3 install --trusted-host pypi.org --no-deps -e .

EXPOSE 5005

CMD ["./start_cts_from_here"]
