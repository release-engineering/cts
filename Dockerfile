FROM fedora:32
LABEL \
    name="CTS" \
    vendor="CTS developers" \
    license="MIT" \
    build-date=""
ARG cacert_url=undefined

WORKDIR /src
RUN cd /etc/yum.repos.d/ \
    && dnf -v -y install 'dnf-command(config-manager)' \
    && dnf config-manager --add-repo http://download-node-02.eng.bos.redhat.com/rel-eng/RCMTOOLS/latest-RCMTOOLS-2-F-\$releasever/compose/Everything/\$basearch/os/ \
    && dnf -v --nogpg -y install httpd python3-mod_wsgi mod_auth_gssapi python3-rhmsg mod_ssl mod_ldap \
        systemd \
        python3-pip \
        python3-fedora \
        python3-funcsigs \
        python3-openidc-client \
        python3-productmd \
        python3-flask-sqlalchemy \
        python3-flask-migrate \
        python3-mock \
        python3-systemd \
        python3-six \
        python3-flask \
        python3-defusedxml \
        python3-httplib2 \
        python3-pyOpenSSL \
        python3-sqlalchemy \
        python3-psycopg2 \
        python3-psutil \
        python3-ldap \
        python3-flask-script \
        python3-flask-login \
        python3-prometheus_client \
    && dnf -v -y install net-tools iproute iputils traceroute \
    && dnf -y clean all \
    && rm -f /tmp/*

RUN if [ "$cacert_url" != "undefined" ]; then \
        cd /etc/pki/ca-trust/source/anchors \
        && curl -O --insecure $cacert_url \
        && update-ca-trust extract; \
    fi

COPY . .

RUN mkdir -p /usr/share/cts && cp contrib/cts.wsgi /usr/share/cts/

RUN pip3 install . --no-deps

WORKDIR /tmp
USER 1001
EXPOSE 8080

ENTRYPOINT httpd -DFOREGROUND
