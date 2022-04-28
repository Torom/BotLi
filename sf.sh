#!/bin/bash
# makefish.sh

# install packages if not already installed
unzip -v &> /dev/null || apt install -y unzip
make -v &> /dev/null ||apt install -y make
g++ -v &> /dev/null || install -y build-essential

# download the Stockfish source code
wget https://github.com/official-stockfish/Stockfish/archive/refs/heads/master.zip
unzip master.zip
cd Stockfish-master/src

# build the executables
# to speedup the building process you can keep only the section that fits your CPU architecture

# build the binary for CPUs without popcnt and bmi2 instructions (e.g. older than Intel Sandy Bridge)
#make profile-build ARCH=x86-64 COMP=gcc
#strip stockfish
#mv stockfish ../../stockfish_x64
#make clean

# build the binary for CPU with popcnt instruction (e.g. Intel Sandy Bridge)
if [ "$(g++ -Q -march=native --help=target | grep mpopcnt | grep enabled)" ] ; then
  make profile-build ARCH=x86-64-modern COMP=gcc
  strip stockfish
  mv stockfish ../../sf
  make clean
fi

cd
