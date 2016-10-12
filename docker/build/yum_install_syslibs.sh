#!/bin/sh
yum install -y epel-release bash
yum install -y glib2-devel libX11-devel libXext-devel libXrender-devel  \
    mesa-libGL-devel libICE-devel libSM-devel ncurses-devel \
    openssh-clients.x86_64 patch.x86_64 dbus-devel gtk2-devel \
    chrpath.x86_64 nano bzip2 xz sudo wget curl curl-devel expat-devel \
    gettext-devel openssl-devel perl-devel zlib-devel bzip2-devel \
    flex rsync
