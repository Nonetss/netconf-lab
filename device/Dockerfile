ARG NETOPEER2_IMAGE=sysrepo/netopeer2@sha256:efc408c392a2970f211227ba3a79fe157281e3d2914b8c4298095e6be4f4fe91
FROM ${NETOPEER2_IMAGE}
RUN apt-get update \
    && apt-get install --no-install-recommends -y iproute2 iputils-ping \
    && rm -rf /var/lib/apt/lists/*
# libnetconf2 filtra del <hello> los modulos YANG 1.1 (nc_send_hello_io llama a
# nc_server_get_cpblts_version con LYS_VERSION_1_0), asi que ietf-interfaces,
# ietf-ip y cualquier modulo propio con "yang-version 1.1;" nunca aparecen como
# capacidad anunciada aunque esten implementados y sean consultables. Se
# recompila con LYS_VERSION_UNDEF para que el hello incluya todos los modulos
# implementados, como haria un switch real.
RUN sed -i \
    's/cpblts = nc_server_get_cpblts_version(session->ctx, LYS_VERSION_1_0);/cpblts = nc_server_get_cpblts_version(session->ctx, LYS_VERSION_UNDEF);/' \
    /src/libnetconf2/src/session.c \
    && cmake --build /src/libnetconf2/build -j"$(nproc)" \
    && cp /src/libnetconf2/build/libnetconf2.so.4.4.5 /usr/lib/x86_64-linux-gnu/libnetconf2.so.4.4.5 \
    && ldconfig
COPY yang/ /opt/sandbox/yang/
COPY init/ /opt/sandbox/init/
COPY device_plugin/ /opt/sandbox/device_plugin/
COPY entrypoint.sh /usr/local/bin/netconf-sandbox-entrypoint
RUN chmod 0755 /usr/local/bin/netconf-sandbox-entrypoint
ENV PYTHONPATH=/opt/sandbox
EXPOSE 830
ENTRYPOINT ["/usr/local/bin/netconf-sandbox-entrypoint"]
