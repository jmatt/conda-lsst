FROM continuumio/centos5_gcc5_base:5.11-5.2-1
MAINTAINER J. Matt Peterson <jmatt@lsst.org>

WORKDIR /build
COPY build/yum_install_syslibs.sh \
     build/yum_install_cmake28.sh \
     build/source_install_git.sh \
     build/install_jmatt_lsstsw.sh \
     build/install_jmatt_conda-lsst.sh \
     build/yum_install_tools.sh \
     build/git-2.2.2.tar.gz \
     /build/

RUN yum install -y epel-release bash

RUN bash yum_install_syslibs.sh && \
    bash yum_install_cmake28.sh

RUN bash source_install_git.sh

RUN bash install_jmatt_lsstsw.sh && \
    bash install_jmatt_conda-lsst.sh

RUN bash yum_install_tools.sh && \
    rm -rf /build/ && \
    useradd -m --uid 1000 -G wheel dev && \
    echo '%wheel ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers && \
    echo 'Defaults:%wheel !requiretty' >> /etc/sudoers && \
    chown -R dev:dev /opt

WORKDIR /home/dev
USER dev
