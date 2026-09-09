#!/usr/bin/env bash
set -euo pipefail

sudo dnf -y update
sudo dnf -y install git curl container-tools firewalld dnf-plugins-core

. /etc/os-release
MAJOR_VERSION="${VERSION_ID%%.*}"

case "$MAJOR_VERSION" in
  8)
    sudo dnf install -y oracle-epel-release-el8
    sudo dnf config-manager --enable ol8_developer_EPEL
    ;;
  9)
    sudo dnf install -y oracle-epel-release-el9
    sudo dnf config-manager --enable ol9_developer_EPEL
    ;;
  10)
    sudo dnf install -y oracle-epel-release-el10
    sudo dnf config-manager --enable ol10_u0_developer_EPEL
    ;;
  *)
    echo "Versao do Oracle Linux nao suportada automaticamente: $VERSION_ID" >&2
    exit 1
    ;;
esac

sudo dnf -y install podman-compose
sudo systemctl enable --now firewalld
sudo firewall-cmd --add-service=http --permanent
sudo firewall-cmd --add-service=https --permanent
sudo firewall-cmd --reload

sudo mkdir -p /opt/reportchart-web
sudo chown opc:opc /opt/reportchart-web

echo "Oracle Linux pronto para podman-compose."
