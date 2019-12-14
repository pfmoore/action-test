@echo off

git clone https://github.com/vim/vim
cd vim\src
nmake /f make_mvc.mak CPUNR=i686 WINVER=0x0500 LUA=.\lua LUA_VER=53
nmake /f make_mvc.mak GUI=yes DIRECTX=yes CPUNR=i686 WINVER=0x0500 LUA=.\lua LUA_VER=53
