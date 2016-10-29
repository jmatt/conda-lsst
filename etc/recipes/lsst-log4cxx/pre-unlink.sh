#!/bin/bash -e

# Reverse the creation of libexpat.so.0 in pre-link.
if [ -e $PREFIX/lib/libexpat.so.0.conda-created ]; then
  rm -f ${PREFIX}/lib/libexpat.so.0
  rm -f $PREFIX/lib/libexpat.so.0.conda-created
fi
