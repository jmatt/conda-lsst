mkdir -p /opt/build
cd /opt/build
cp /build/git-2.2.2.tar.gz /opt/build/
tar xfvz ./git-2.2.2.tar.gz
rm ./git-2.2.2.tar.gz
cd git-2.2.2
make configure
./configure --prefix=/usr
make all
make install
