FROM debian:bookworm

ENV container=docker \
    DEBIAN_FRONTEND=noninteractive \
    MLA_USER=mla

# systemd + sshd + sudo + python. python3-apt is here so the `apt` module
# has something to introspect later; iproute2/ping just make debugging nicer.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        systemd systemd-sysv dbus \
        openssh-server sudo \
        python3 python3-apt \
        iproute2 iputils-ping procps ca-certificates \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# Mask units that are pointless in a container and only slow down / spam the boot.
RUN systemctl mask \
        getty.target console-getty.service \
        systemd-timesyncd.service systemd-resolved.service \
        dev-hugepages.mount sys-fs-fuse-connections.mount \
        systemd-firstboot.service || true

# --- Test account: non-root, sudo requires a password (matches the real
#     correction environment) -- the same account password ("mla") is used
#     for SSH password auth (ssh_password) and for sudo (-S), reproducing
#     what the "sudo -n" -> "sudo -S" fix now relies on.
RUN useradd --create-home --shell /bin/bash "${MLA_USER}" \
 && echo "${MLA_USER}:mla" | chpasswd \
 && echo "${MLA_USER} ALL=(ALL) ALL" > "/etc/sudoers.d/${MLA_USER}" \
 && chmod 0440 "/etc/sudoers.d/${MLA_USER}" \
 && install -d -o "${MLA_USER}" -g "${MLA_USER}" -m 700 "/home/${MLA_USER}/.ssh"

# --- sshd: host keys baked into the image so they stay stable across
#     `up`/`down` cycles (they only change on a rebuild). Password auth on,
#     root login off.
RUN ssh-keygen -A \
 && printf 'PasswordAuthentication yes\nPermitRootLogin no\nPubkeyAuthentication yes\n' \
        > /etc/ssh/sshd_config.d/00-mla.conf \
 && systemctl enable ssh

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 22
STOPSIGNAL SIGRTMIN+3
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["/sbin/init"]
