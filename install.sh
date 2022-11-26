#!/bin/sh

# detecting the platform
os="$(uname)"
case $os in
    Linux)
        os='linux'
        ;;
    *)
        echo 'os not supported'
        exit 2
        ;;
esac

arch="$(uname -m)"
case $arch in
    x86_64|amd64)
        arch='amd64'
        ;;
    aarch64)
        arch='arm64'
        ;;
    arm*)
        arch='arm'
        ;;
    *)
        echo 'architecture not supported'
        exit 2
        ;;
esac

if [ -f /usr/bin/apt ]; then
    distro='ubuntu'
    os_ver=$(cat /etc/lsb-release | grep DISTRIB_RELEASE | cut -d= -f2)
elif [ -f /sbin/apk ]; then
    distro='alpine'
    os_ver=$(head -n1 /etc/apk/repositories | sed -e 's/.*\/v\(.*\)\/.*/\1/g')
else
    echo 'os distro not supported'
    exit 2
fi

# find and delete
if [ $1 = "-delete" ]; then
    apt-get remove --purge -yqq python3-libtorrent || \
        apt-get remove --purge -yqq python-libtorrent
    find /usr -iname "*libtorrent*" -exec rm -rf {} +
    exit 0
fi

# parsing lt_tag
lt_tag="$1"
lt_ver=$(echo $lt_tag | cut -d- -f1)
lt_build=$(echo $lt_tag | cut -d- -f2)

# making download url
url_base="https://github.com/by275/docker-libtorrent/releases/download/$lt_tag/"
filename="libtorrent-$lt_ver-$distro$os_ver-$arch.tar.gz"
down_url=$url_base$filename

if [ $distro = "ubuntu" ]; then
    # wait until apt-get not used by other process
    while ps -opid= -C apt-get > /dev/null; do sleep 1; done
    # apt-get update if never done during the past 24 hours
    [ ! -d /var/lib/apt/lists/partial ] && apt-get update -yqq
    [ -z "$(find -H /var/lib/apt/lists -maxdepth 0 -mtime -1)" ] && apt-get update -yqq 

    echo ""
    echo "===================================================================="
    echo "Installing pre-built libs if possible ..."
    echo "===================================================================="
    echo ""
    curl -sLJ "$down_url" | tar xvz -C /
    
    if [ $? = "0" ]; then
        echo ""
        echo "===================================================================="
        echo "Installing runtime packages ..."
        echo "===================================================================="
        echo ""
        apt-get install -y --no-install-recommends \
            'libboost-python[0-9.]+$'
    else
        echo ""
        echo "===================================================================="
        echo "Installing ubuntu official package as the previous step failed"
        echo "===================================================================="
        echo ""
        apt-get install -y python3-libtorrent || \
            apt-get install -y python-libtorrent
    fi
elif [ $distro = "alpine" ]; then
    echo ""
    echo "===================================================================="
    echo "Installing pre-built libs ..."
    echo "===================================================================="
    echo ""
    curl -sLJ "$down_url" | tar xvz -C /

    echo ""
    echo "===================================================================="
    echo "Installing runtime packages ..."
    echo "===================================================================="
    echo ""
    apk add --no-cache \
        libstdc++ \
        boost-system \
        boost-python3
fi

# checking installation
pyver=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
export PYTHONPATH=/usr/lib/python$pyver/site-packages
LIBTORRENT_VER=$(python3 -c 'import libtorrent as lt; print(lt.version)')

if [ $? = "0" ]; then
    echo ""
    echo "===================================================================="
    echo "Libtorrent v$LIBTORRENT_VER has successfully installed"
    echo "===================================================================="
    echo ""
else
    echo ""
    echo "===================================================================="
    echo "Something went wrong !!!"
    echo "===================================================================="
    echo ""
fi

exit 0
